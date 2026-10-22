"""Запись с микрофона: int16 mono 16 kHz + текущий уровень громкости."""
from __future__ import annotations

import threading
import time

import numpy as np
import sounddevice as sd


class MicError(RuntimeError):
    pass


class MicRecorder:
    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._started_at = 0.0
        self.raw_level = 0.0  # rms 0..1, читается из GUI-потока

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started_at if self._stream else 0.0

    def start(self) -> None:
        if self._stream is not None:
            return
        with self._lock:
            self._frames = []
        self.raw_level = 0.0
        self._started_at = time.monotonic()

        def callback(indata, frames, time_info, status):  # поток PortAudio
            with self._lock:
                self._frames.append(indata.copy())
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)) / 32768.0)
            self.raw_level = min(1.0, rms * 6.0)  # нормируем, чтобы бар жил

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate, channels=1, dtype="int16",
                blocksize=0, callback=callback,
            )
            self._stream.start()
        except OSError as e:
            self._stream = None
            msg = str(e)
            if "-9986" in msg or "unhandled" in msg.lower():
                raise MicError("Нет доступа к микрофону. Разреши доступ: "
                               "Системные настройки → Конфиденциальность → Микрофон.") from e
            raise MicError(f"Микрофон не открылся: {msg}") from e

    def stop(self) -> tuple[np.ndarray, float]:
        """Вернуть (samples int16 mono, длительность в секундах)."""
        dur = self.elapsed
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            frames = self._frames
            self._frames = []
        if not frames:
            return np.zeros(0, dtype=np.int16), dur
        audio = np.concatenate(frames, axis=0).reshape(-1)
        return audio, dur

    def cancel(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            self._frames = []
        self.raw_level = 0.0
