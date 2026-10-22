"""GigaAM Диктовка — правая ⌘: нажал, наговорил, нажал ещё раз — текст под курсором.

Запуск:  .venv/bin/python app/main.py          (обычный режим)
         .venv/bin/python app/main.py --demo   (демо-цикл для скриншотов)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime

from PySide6.QtCore import QObject, QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QPen
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config import (
    APP_NAME, DB_PATH, MAX_RECORD_SEC, MIN_RECORD_SEC, MODEL_NAME, ORG_NAME,
    PROJECT_DIR,
)
from dictionary import Dictionary, DictionaryWindow
from history import HistoryStore, HistoryWindow, human_dur
from hotkey import (
    RightCommandWatcher,
    listen_event_access_ok,
    open_accessibility_settings,
    request_listen_event_access,
)
from overlay import OverlayManager
from recorder import MicError, MicRecorder

LOG = logging.getLogger("gigaam")


def mic_pixmap(record: bool = False) -> QPixmap:
    """Белая иконка меню-бара: чистый микро; во время записи — с красной точкой."""
    pm = QPixmap(44, 44)
    pm.setDevicePixelRatio(2.0)  # ретина: логический размер 22×22
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    white = QColor(255, 255, 255, 245)
    pen = QPen(white, 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(white)
    # капсула микрофона
    p.drawRoundedRect(QRectF(8.5, 3.5, 5.0, 8.5), 2.5, 2.5)
    # дуга-держатель
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(6.5, 6.0, 9.0, 9.0), 0, -180 * 16)
    # ножка и база
    p.drawLine(QPointF(11.0, 15.0), QPointF(11.0, 17.5))
    p.drawLine(QPointF(8.2, 18.2), QPointF(13.8, 18.2))
    if record:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 96, 92))
        p.drawEllipse(QRectF(16.5, 1.0, 5.0, 5.0))
    p.end()
    return pm


def _osascript(script: str) -> str:
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as e:
        return str(e)


def setup_logging() -> None:
    """Журнал в файл: что нажалось, что с распознаванием и вставкой."""
    import logging
    from config import DATA_DIR
    log = logging.getLogger("gigaam")
    log.setLevel(logging.INFO)
    fh = logging.FileHandler(DATA_DIR / "app.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%d.%m %H:%M:%S"))
    log.addHandler(fh)

    def hook(kind, value, tb):
        log.error("НЕПЕРЕХВАЧЕНО: %s: %s", kind.__name__, value, exc_info=(kind, value, tb))
        sys.__excepthook__(kind, value, tb)

    sys.excepthook = hook
    log.info("=== запуск %s (pid %s) ===", APP_NAME, os.getpid())
    log.info("PATH: %s", os.environ.get("PATH", ""))


def app_bundle_path() -> str:
    return str(PROJECT_DIR / "GigaAM.app")


def activate_app(info: dict) -> bool:
    """Вернуть фокус приложению по pid (для вставки из истории)."""
    try:
        from AppKit import NSRunningApplication
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(info["pid"])
        app.activateWithOptions_(1 << 1)  # ignoring other apps
        return True
    except Exception:
        return False


class Controller(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(ORG_NAME, "GigaAM-Dictation")
        self.store = HistoryStore(DB_PATH)
        self.engine = AsrEngineWrapper(self)
        self.recorder = MicRecorder()
        self.overlay = OverlayManager()
        self.watcher = RightCommandWatcher()
        self.history_win: HistoryWindow | None = None
        self.dictionary = Dictionary()
        self.dict_win: DictionaryWindow | None = None
        self.tray: QSystemTrayIcon | None = None
        self.state = "idle"  # idle | recording | transcribing
        self._record_t0 = 0.0
        self._last_hint = 0.0
        self._inserter = None

        # --- настройки по умолчанию
        if self.settings.value("insert_apps") is None:
            self.settings.setValue("insert_apps", True)
        if self.settings.value("keep_clipboard") is None:
            self.settings.setValue("keep_clipboard", True)

        self.engine.stateChanged.connect(self._on_engine_state)
        self.engine.transcribeDone.connect(self._on_text)
        self.engine.transcribeFailed.connect(self._on_asr_failed)
        self.engine.engine.transcribeProgress.connect(self._on_progress)
        self.engine.engine.transcribeCancelled.connect(self._on_cancelled)
        self.watcher.pressed.connect(self.on_hotkey)
        self.watcher.escPressed.connect(self.on_esc)
        self.watcher.error.connect(
            lambda m: self.overlay.show_error(f"Хоткей: {m}", linger=6.0))
        self.overlay.historyRequested.connect(self.open_history)

        self._max_timer = QTimer(self)
        self._max_timer.setSingleShot(True)
        self._max_timer.setInterval(int(MAX_RECORD_SEC * 1000))
        self._max_timer.timeout.connect(self._finish_recording)

    # --- настройки-обёртки
    @property
    def insert_enabled(self) -> bool:
        return self.settings.value("insert_apps", True, type=bool)

    @property
    def keep_clipboard(self) -> bool:
        return self.settings.value("keep_clipboard", True, type=bool)

    def inserter(self):
        if self._inserter is None:
            import inserter as ins
            self._inserter = ins
        return self._inserter

    # --- горячая клавиша
    def on_hotkey(self) -> None:
        LOG.info("⌘R нажат, состояние=%s, модель=%s", self.state, self.engine.engine.state)
        if self.state == "idle":
            if self.engine.engine.state != "ready":
                now = time.monotonic()
                if now - self._last_hint > 2.5:
                    self._last_hint = now
                    if self.engine.engine.state == "error":
                        self.overlay.show_error("Модель не загрузилась — смотри меню в трее",
                                                linger=4.0)
                    else:
                        self.overlay.show_loading_hint()
                return
            try:
                self.recorder.start()
            except MicError as e:
                self.overlay.show_error(str(e), linger=6.0)
                return
            self.state = "recording"
            self._record_t0 = time.monotonic()
            self._max_timer.start()
            self.overlay.show_recording(lambda: self.recorder.raw_level)
            self._update_tray()
        elif self.state == "recording":
            self._finish_recording()
        elif self.state == "transcribing":
            now = time.monotonic()
            if now - self._last_hint > 2.0:
                self._last_hint = now
                self.overlay.show_info("Секунду…", "договариваю текст", 1.6)

    def on_esc(self) -> None:
        if self.state == "recording":
            self.recorder.cancel()
            self._max_timer.stop()
            self.state = "idle"
            self.overlay.hide_all()
            self.overlay.show_info("Отменено", "запись не сохранена", 2.0)
            self._update_tray()
        elif self.state == "transcribing":
            self.engine.engine.cancel()
            self.overlay.show_info("Останавливаю…", "сохраняю то, что успел распознать",
                                   2.0)

    def _finish_recording(self) -> None:
        self._max_timer.stop()
        samples, dur = self.recorder.stop()
        if dur < MIN_RECORD_SEC:
            self.state = "idle"
            self.overlay.hide_all()
            self._update_tray()
            self.overlay.show_info("Слишком коротко",
                                   "похоже, это было случайное нажатие", 2.0)
            return
        self.state = "transcribing"
        self.overlay.show_transcribing()
        self.engine.transcribe_async(samples, dur)

    def _on_progress(self, done: int, total: int) -> None:
        self.overlay.trans.set_progress(done, total)

    def _on_cancelled(self, dur: float, text: str) -> None:
        self.state = "idle"
        self._update_tray()
        text = (text or "").strip()
        if text:
            self.store.add(text, dur)
            self.overlay.show_info("Отменено", "текст сохранил в историю", 3.0)
        else:
            self.overlay.show_info("Отменено", "", 2.0)

    # --- результаты
    def _on_text(self, dur: float, text: str) -> None:
        self.state = "idle"
        self._update_tray()
        text = (text or "").strip()
        LOG.info("распознано (%.1fс): %.80s", dur, text)
        if not text:
            self.overlay.show_error(
                "Не расслышал. Попробуй ещё раз и говори чуть ближе к микрофону.")
            return
        try:
            text = self.dictionary.apply(text)
        except Exception as e:
            LOG.exception("словарь не применился: %s", e)
        inserted = False
        app_name = None
        clip = QApplication.clipboard()
        if self.insert_enabled:
            try:
                res = self.inserter().insert_text(text, keep_clipboard=self.keep_clipboard)
                inserted = bool(res.get("ok"))
                app_name = res.get("app")
                LOG.info("вставка: %s (метод=%s, ошибка=%s)", res, res.get("method"), res.get("error"))
                if not inserted:
                    clip.setText(text)  # не вставилось — хотя бы в буфере лежит
            except Exception as e:
                LOG.exception("вставка упала исключением")
                clip.setText(text)
                self.overlay.show_error(f"Вставить не удалось: {e}")
        else:
            clip.setText(text)
        self.store.add(text, dur)
        if inserted:
            title = "Вставлено"
        else:
            title = "Скопировано"
        parts = [human_dur(dur), datetime.now().strftime("%H:%M")]
        if app_name:
            parts.insert(0, app_name)
        self.overlay.show_result(title, " · ".join(parts), text, ok=True)

    def _on_asr_failed(self, msg: str) -> None:
        LOG.error("распознавание упало: %s", msg)
        self.state = "idle"
        self._update_tray()
        self.overlay.show_error("Распознать не получилось — подробности в журнале")

    def _on_engine_state(self, st: str) -> None:
        LOG.info("движок: %s (устройство=%s, ошибка=%s)",
                 st, self.engine.engine.device_used, self.engine.engine.load_error)
        if st == "error":
            err = self.engine.engine.load_error or "неизвестная ошибка"
            if self.tray:
                self.tray.showMessage(APP_NAME, f"Модель не загрузилась: {err}",
                                      QSystemTrayIcon.MessageIcon.Critical, 6000)
        self._update_tray()

    # --- история
    def open_history(self) -> None:
        if self.history_win is None:
            self.history_win = HistoryWindow(self.store, self)
            self.history_win.insertRequested.connect(self._insert_from_history)
        self.history_win.open_and_focus(HistoryWindow.TAB_HISTORY)

    def open_dictionary(self) -> None:
        if self.dict_win is None:
            self.dict_win = DictionaryWindow(self.dictionary)
            self.dict_win.saved.connect(self._on_dict_saved)
        self.dict_win.open_and_focus()

    def _on_dict_saved(self, n: int) -> None:
        self.overlay.show_result(
            "Словарь сохранён", f"{n} замен",
            "Теперь эти слова будут писаться правильно.", ok=True)

    def _insert_from_history(self, text: str) -> None:
        # перед вставкой возвращаем фокус приложению, которое было активно
        # до открытия окна истории — иначе Cmd+V уйдёт в саму историю
        prev = getattr(self.history_win, "prev_app", None)
        if prev and prev.get("pid"):
            activate_app(prev)
            time.sleep(0.25)
        try:
            res = self.inserter().insert_text(text, keep_clipboard=self.keep_clipboard)
            if not res.get("ok"):
                QApplication.clipboard().setText(text)
                self.overlay.show_info("Не вставилось", "текст в буфере обмена", 3.0)
            else:
                app_name = res.get("app")
                self.overlay.show_info(
                    "Вставлено" + (f" · {app_name}" if app_name else ""),
                    "текст из истории", 2.0)
        except Exception as e:
            QApplication.clipboard().setText(text)
            self.overlay.show_error(f"Вставить не удалось: {e}")

    # --- системное
    def build_tray(self) -> None:
        self.tray = QSystemTrayIcon(QIcon(mic_pixmap(False)))
        menu = QMenu()
        self._menu = menu  # держим ссылку: без неё Python соберёт меню мусорщиком
        self.status_action = QAction("Прогреваю модель…")
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        menu.addSeparator()

        hist = QAction("История", menu)
        hist.triggered.connect(self.open_history)
        menu.addAction(hist)

        dict_act = QAction("Словарь замен…", menu)
        dict_act.triggered.connect(self.open_dictionary)
        menu.addAction(dict_act)

        self.act_insert = QAction("Вставлять текст в приложения", menu)
        self.act_insert.setCheckable(True)
        self.act_insert.setChecked(self.insert_enabled)
        self.act_insert.toggled.connect(self.set_insert)
        menu.addAction(self.act_insert)

        self.act_clip = QAction("Восстанавливать буфер обмена", menu)
        self.act_clip.setCheckable(True)
        self.act_clip.setChecked(self.keep_clipboard)
        self.act_clip.setEnabled(self.insert_enabled)
        self.act_clip.toggled.connect(self.set_keep_clipboard)
        menu.addAction(self.act_clip)

        self.act_login = QAction("Запускать при входе в систему", menu)
        self.act_login.setCheckable(True)
        # состояние из кэша настроек: живой запрос к System Events дёргал бы
        # вопрос про «Автоматизацию»; точная синхронизация — во вкладке «Настройки»
        self.act_login.setChecked(self.settings.value("autostart", False, type=bool))
        self.act_login.toggled.connect(self.set_autostart)
        menu.addAction(self.act_login)

        menu.addSeparator()
        perms = QAction("Права и доступы…", menu)
        perms.triggered.connect(self._open_permissions)
        menu.addAction(perms)
        quit_ = QAction("Выход", menu)
        quit_.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_)

        # БЕЗ setContextMenu: в маке он открывает меню на ЛЮБОЙ клик по значку.
        # Левый клик = центр (история/настройки), правый = меню (см. _on_tray_click).
        self.tray.setToolTip(f"{APP_NAME}\nПравая ⌘ — наговорить, ещё раз — вставить")
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()
        self._update_tray()

    def _on_tray_click(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_history()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # правый клик: показать меню там, где курсор
            from PySide6.QtGui import QCursor
            self._menu.popup(QCursor.pos())

    def _open_permissions(self) -> None:
        self.open_permissions()

    # --- настройки (единая точка: трей и вкладка «Настройки» пишут сюда)
    def set_insert(self, on: bool) -> None:
        self.settings.setValue("insert_apps", bool(on))
        if hasattr(self, "act_insert"):
            self._sync_action(self.act_insert, bool(on))
        if hasattr(self, "act_clip"):
            self.act_clip.setEnabled(bool(on))

    def set_keep_clipboard(self, on: bool) -> None:
        self.settings.setValue("keep_clipboard", bool(on))
        if hasattr(self, "act_clip"):
            self._sync_action(self.act_clip, bool(on))

    def set_autostart(self, on: bool) -> None:
        set_login_item(bool(on))
        ok = is_login_item()
        self.settings.setValue("autostart", ok)  # кэш для меню-бара
        if hasattr(self, "act_login"):
            self._sync_action(self.act_login, ok)

    def _sync_action(self, action: QAction, checked: bool) -> None:
        action.blockSignals(True)
        action.setChecked(checked)
        action.blockSignals(False)

    def open_permissions(self) -> None:
        open_accessibility_settings()
        self.overlay.show_error(
            "Включи переключатель приложения в «Конфиденциальность → "
            "Мониторинг ввода» и «Универсальный доступ», потом перезапусти.",
            linger=8.0)

    def _update_tray(self) -> None:
        if not self.tray:
            return
        st = self.engine.engine.state
        if self.state == "recording":
            self.tray.setIcon(QIcon(mic_pixmap(True)))
        else:
            self.tray.setIcon(QIcon(mic_pixmap(False)))
        if st == "ready":
            dev = self.engine.engine.device_used or "cpu"
            self.status_action.setText(f"● Готово · {MODEL_NAME} · {dev}")
        elif st == "error":
            self.status_action.setText("● Модель не загрузилась")
        else:
            self.status_action.setText("● Прогреваю модель…")

    # --- права
    def ensure_permissions(self) -> None:
        """Нужны два права: Мониторинг ввода (ловить ⌘R) и Универсальный
        доступ (слать Cmd+V). Запрашиваем оба сразу, дальше — ждём."""
        ins = self.inserter()
        need_any = (not listen_event_access_ok()) or (not ins.check_accessibility())
        if not need_any:
            return
        request_listen_event_access()          # системный вопрос №1
        ins.check_accessibility(prompt=True)   # системный вопрос №2
        QTimer.singleShot(
            1500, lambda: self.overlay.show_error(
                "Мак попросит два разрешения: «Мониторинг ввода» и "
                "«Универсальный доступ». Разреши оба — и перезапусти "
                "приложение (значок → Выход → открыть заново).", linger=12.0))

        def check():
            ok = listen_event_access_ok() and ins.check_accessibility()
            if ok:
                self.overlay.show_result(
                    "Готово!", "права выданы",
                    "Жми правую ⌘ и говори. Ещё раз — текст вставится под курсор. "
                    "Если что-то не вставляется — перезапусти приложение.",
                    ok=True)
            else:
                QTimer.singleShot(4000, check)

        QTimer.singleShot(5000, check)

    def start(self) -> None:
        self.engine.engine.start_loading()
        if not self.watcher.start():
            self.overlay.show_error(
                "Слушатель клавиатуры не запустился — правая ⌘ не заработает. "
                "Подробности в журнале.", linger=8.0)
        self.ensure_permissions()


class AsrEngineWrapper(QObject):
    """Тонкая обёртка, чтобы сигналам было куда приходить из потоков."""

    from PySide6.QtCore import Signal
    stateChanged = Signal(str)
    transcribeDone = Signal(float, str)
    transcribeFailed = Signal(str)

    def __init__(self, controller: Controller) -> None:
        super().__init__()
        from asr import AsrEngine
        from config import DEVICE
        self.engine = AsrEngine(MODEL_NAME, DEVICE)
        self.engine.stateChanged.connect(self.stateChanged)
        self.engine.transcribeDone.connect(self.transcribeDone)
        self.engine.transcribeFailed.connect(self.transcribeFailed)

    def transcribe_async(self, samples, dur) -> None:
        self.engine.transcribe_async(samples, dur)


def is_login_item() -> bool:
    out = _osascript(
        'tell application "System Events" to get the path of every login item')
    return app_bundle_path() in (out or "")


def set_login_item(on: bool) -> None:
    if on:
        _osascript(
            'tell application "System Events" to make login item at end '
            f'with properties {{path:"{app_bundle_path()}", hidden:false}}')
    else:
        _osascript(
            'tell application "System Events" to delete login items '
            f'whose path is "{app_bundle_path()}"')


def run_demo() -> None:
    """Демо-цикл для скриншотов: запись → распознавание → результат."""
    import math
    import random

    ctl = Controller()
    ctl.build_tray()
    ctl.overlay.show_recording(lambda: 0.35 + 0.3 * math.sin(time.monotonic() * 3)
                               + random.random() * 0.3)
    QTimer.singleShot(4000, lambda: (ctl.overlay.show_transcribing()))
    QTimer.singleShot(6500, lambda: ctl.overlay.show_result(
        "Вставлено", "0:07 · 14:32",
        "Привет! Это тестовая диктовка — проверяем, как ложится текст "
        "с пунктуацией и большими буквами."))
    QTimer.singleShot(14000, QApplication.instance().quit)


def main() -> None:
    # под launchd PATH урезан: без /opt/homebrew/bin модель не находит ffmpeg.
    # ВАЖНО: до setup_logging, чтобы журнал показывал уже исправленный PATH
    os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setQuitOnLastWindowClosed(False)

    # тулза живёт в меню-баре: политика Accessory убирает из дока и делает
    # окна полноправными жителями всех Space (включая полноэкранные)
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory)
    except Exception:
        pass

    ctl = Controller()
    ctl.build_tray()

    if "--demo" in sys.argv:
        run_demo()
    else:
        ctl.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
