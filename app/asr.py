"""Движок GigaAM: загрузка модели в фоне + расшифровка без блокировки GUI."""
from __future__ import annotations

import os
import tempfile
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal

# --- Нарезка длинного аудио -------------------------------------------------
# GigaAM обучена на кусках до ~25 c: более длинное аудио за один проход
# распознаётся плохо. Всё длиннее SPLIT_OVER_SEC режем по паузам на куски
# не длиннее CHUNK_SEC и расшифровываем по отдельности.
CHUNK_SEC = 20.0        # максимальная длина куска
SPLIT_OVER_SEC = 21.0   # короче — шлём в модель одним файлом, как раньше
PAUSE_ZONE_SEC = 0.3    # ширина «тихой зоны», в которой ищем точку реза
RMS_FRAME_SEC = 0.05    # кадр, по которому считается RMS


def split_on_pauses(
    samples: np.ndarray,
    sr: int = 16000,
    max_chunk_sec: float = CHUNK_SEC,
    search_sec: float = 4.0,
) -> list[np.ndarray]:
    """Режет int16 mono на куски длиной <= max_chunk_sec.

    Точка реза — самая тихая зона шириной PAUSE_ZONE_SEC в окне вокруг
    идеальной границы (i * max_chunk_sec): назад до search_sec, вперёд —
    насколько позволяет лимит длины куска (правее ideal резать нельзя,
    иначе кусок превысит max_chunk_sec). Тишины в окне нет (тише среднего
    по записи ничего не нашлось) — режем ровно по границе. RMS считается
    по кадрам RMS_FRAME_SEC. Куски в сумме покрывают весь исходный
    массив без потерь.
    """
    n = len(samples)
    max_len = int(max_chunk_sec * sr)
    if n <= max_len:
        return [samples]

    frame = max(1, int(RMS_FRAME_SEC * sr))
    zone_len = int(PAUSE_ZONE_SEC * sr)
    frames_per_zone = max(1, zone_len // frame)
    n_frames = n // frame
    if n_frames == 0:
        return [samples]

    # RMS по кадрам 50 мс (хвост, не влезающий в кадр, не участвует)
    fr = samples[: n_frames * frame].reshape(n_frames, frame).astype(np.float64)
    rms = np.sqrt((fr ** 2).mean(axis=1))
    # средний RMS скользящего окна шириной 300 мс: zone_rms[j] — зона с кадра j
    zone_rms = np.convolve(rms, np.full(frames_per_zone, 1.0 / frames_per_zone), mode="valid")
    global_rms = float(rms.mean())

    bounds = [0]
    while n - bounds[-1] > max_len:
        ideal = bounds[-1] + max_len
        lo = max(bounds[-1] + frame, ideal - int(search_sec * sr))
        hi = min(bounds[-1] + max_len, n)  # правее ideal резать нельзя
        cut = ideal  # запасной вариант: ровно по границе
        jlo = lo // frame
        # зона целиком левее hi, чтобы её центр не вылез за лимит длины
        jhi = min((hi - zone_len) // frame, len(zone_rms) - 1)
        if jhi >= jlo:
            j = jlo + int(np.argmin(zone_rms[jlo : jhi + 1]))
            if float(zone_rms[j]) <= global_rms:  # пауза реально тише речи
                cut = j * frame + zone_len // 2   # середина тихой зоны
        # страховка: кусок не длиннее max_len и не пустой
        cut = min(max(cut, bounds[-1] + frame), bounds[-1] + max_len)
        bounds.append(cut)
    bounds.append(n)
    return [samples[a:b] for a, b in zip(bounds, bounds[1:]) if b > a]


class AsrEngine(QObject):
    stateChanged = Signal(str)          # "loading" | "ready" | "error"
    transcribeDone = Signal(float, str)  # (длительность аудио, текст)
    transcribeFailed = Signal(str)
    transcribeProgress = Signal(int, int)  # (кусок, всего кусков)
    transcribeCancelled = Signal(float, str)  # (длительность, что успели)

    def __init__(self, model_name: str, device: str = "auto") -> None:
        super().__init__()
        self.model_name = model_name
        self.device_pref = device
        self.model = None
        self._onnx = None            # лёгкий бэкенд int8-ONNX (без PyTorch)
        self.backend: str | None = None
        self.device_used: str | None = None
        self.state = "init"
        self._busy = False
        self._cancel = False
        self._load_error: str | None = None
        self._load_started = 0.0
        self._load_elapsed = 0.0

    def cancel(self) -> None:
        """Попросить остановить распознавание (Esc во время «Распознаю…»)."""
        self._cancel = True

    @property
    def load_seconds(self) -> float:
        return self._load_elapsed

    def start_loading(self) -> None:
        self._load_started = time.monotonic()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        self.state = "loading"
        self.stateChanged.emit(self.state)
        try:
            # Путь 1 (основной): int8-ONNX через onnx-asr — без PyTorch,
            # в 3-4 раза меньше памяти, частично на нейродвижке Apple.
            try:
                import onnx_asr
            except ImportError:
                onnx_asr = None
            if onnx_asr is not None:
                try:
                    self._onnx = onnx_asr.load_model(
                        "gigaam-v3-e2e-ctc", quantization="int8")
                    self.backend = "onnx-int8"
                    if not self._warmup_ok():
                        raise RuntimeError("onnx warmup failed")
                except Exception:
                    self._onnx = None
                    self.backend = None
            # Путь 2 (запасной): полный PyTorch gigaam (MPS с откатом на CPU).
            if self._onnx is None:
                import gigaam
                import torch

                dev = "cpu"
                if self.device_pref in ("auto", "mps") and torch.backends.mps.is_available():
                    dev = "mps"
                try:
                    self.model = gigaam.load_model(self.model_name, device=dev)
                    if not self._warmup_ok():
                        raise RuntimeError("warmup failed")
                except Exception:
                    if dev == "mps":
                        dev = "cpu"
                        self.model = gigaam.load_model(self.model_name, device=dev)
                        if not self._warmup_ok():
                            raise
                    else:
                        raise
                self.backend = f"torch-{dev}"
            self.device_used = self.backend
            self._load_elapsed = time.monotonic() - self._load_started
            self.state = "ready"
            self.stateChanged.emit(self.state)
        except Exception as e:
            self._load_error = str(e)
            self.state = "error"
            self.stateChanged.emit(self.state)

    def _warmup_ok(self) -> bool:
        """Прогрев: заодно проверяем, что на этом устройстве реально считает."""
        silence = np.zeros(16000 // 2, dtype=np.int16)  # 0.5 c тишины
        try:
            self.transcribe_sync(silence)
            return True
        except Exception:
            return False

    def transcribe_sync(self, samples: np.ndarray) -> str:
        """Расшифровать int16 mono 16k. Блокирующий, вызывать из фонового потока.

        Аудио длиннее SPLIT_OVER_SEC режется по паузам (split_on_pauses),
        каждый кусок расшифровывается отдельно, тексты склеиваются пробелом.
        """
        if len(samples) <= int(SPLIT_OVER_SEC * 16000):
            return self._transcribe_one(samples)
        texts = [self._transcribe_one(chunk) for chunk in split_on_pauses(samples)]
        return " ".join(t for t in texts if t)

    def _transcribe_one(self, samples: np.ndarray) -> str:
        """Расшифровать один кусок: int8-ONNX напрямую из массива,
        либо (запасной путь) torch-модель через временный wav."""
        if self._onnx is not None:
            text = self._onnx.recognize(samples.astype("float32") / 32768.0)
            return (text or "").strip()

        import soundfile as sf

        fd, path = tempfile.mkstemp(suffix=".wav", prefix="dictation-")
        os.close(fd)
        try:
            sf.write(path, samples, 16000, subtype="PCM_16")
            result = self.model.transcribe(path)
            text = getattr(result, "text", None)
            if not isinstance(text, str):
                text = str(result)
            return (text or "").strip()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def transcribe_async(self, samples: np.ndarray, audio_dur: float) -> None:
        if self.state != "ready" or self._busy:
            self.transcribeFailed.emit("Движок занят или ещё не готов")
            return
        self._busy = True
        self._cancel = False

        def work():
            try:
                chunks = split_on_pauses(samples)
                total = len(chunks)
                self.transcribeProgress.emit(0, total)
                parts = []
                for i, chunk in enumerate(chunks):
                    if self._cancel:
                        break
                    parts.append(self._transcribe_one(chunk))
                    self.transcribeProgress.emit(i + 1, total)
                text = " ".join(t for t in parts if t)
                if self._cancel:
                    self.transcribeCancelled.emit(audio_dur, text)
                else:
                    self.transcribeDone.emit(audio_dur, text)
            except Exception as e:
                self.transcribeFailed.emit(str(e))
            finally:
                self._busy = False

        threading.Thread(target=work, daemon=True).start()

    @property
    def load_error(self) -> str | None:
        return self._load_error
