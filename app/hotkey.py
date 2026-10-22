"""Глобальная ловля правой Command (⌘R) и Esc.

Режим «нажал — говоришь — нажал ещё раз». События приходят из потока pynput,
наружу отдаём Qt-сигналы (Qt сам превращает их в потокобезопасные вызовы).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class RightCommandWatcher(QObject):
    """Сигналы шлются из потока pynput; Qt превращает их в потокобезопасные вызовы."""

    pressed = Signal()      # правая ⌘ — старт/финиш диктовки
    escPressed = Signal()   # Esc — отмена записи
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._listener = None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception as e:  # pragma: no cover
            self.error.emit(f"Не запустился слушатель клавиатуры: {e}")
            return False

        def on_press(key):
            if key == keyboard.Key.cmd_r:
                self.pressed.emit()
            elif key == keyboard.Key.esc:
                self.escPressed.emit()

        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception as e:
            self.error.emit(f"Слушатель клавиатуры не стартовал: {e}")
            return False

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


def listen_event_access_ok() -> bool:
    """True, если приложению уже разрешено слушать клавиатуру (Accessibility)."""
    try:
        from Quartz import CGPreflightListenEventAccess
        return bool(CGPreflightListenEventAccess())
    except Exception:
        return True  # не смогли спросить — не блокируем, пусть пробует


def request_listen_event_access() -> None:
    """Показать системный запрос права на слушание клавиатуры."""
    try:
        from Quartz import CGRequestListenEventAccess
        CGRequestListenEventAccess()
    except Exception:
        pass


def open_accessibility_settings() -> None:
    import subprocess
    subprocess.Popen(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
