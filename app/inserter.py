"""inserter.py — вставка текста в то приложение macOS, где сейчас фокус.

Основной путь — insert_text(): имитация Cmd+V.
    1. Сохранить текущее содержимое буфера обмена (NSPasteboard, все типы).
    2. Положить в буфер заданный текст.
    3. Синтезировать Cmd+V через Quartz CGEvent (keycode 9 'v' + cmd-флаг,
       keyDown+keyUp в kCGHIDEventTap).
    4. Подождать paste_delay (по умолчанию 0.35 с), чтобы целевое приложение
       успело прочитать буфер.
    5. Восстановить прежний буфер (если keep_clipboard=True).

Резервный путь — type_text(): вся строка одним событием через
CGEventKeyboardSetUnicodeString, буфер обмена не трогается. Годится для
случаев, когда трогать буфер нельзя; ограничение: очень длинные строки
одно событие может не донести целиком (исторический лимит ~20 UTF-16
символов на событие, на современных macOS больше, но не бесконечность).

МОДУЛЬ НЕ БРОСАЕТ ИСКЛЮЧЕНИЯ. Любая ошибка превращается в результат:
    {"ok": bool, "method": "clipboard" | "typing", "error": None | str}

Права: постинг CGEvent требует Accessibility (Системные настройки ->
Конфиденциальность и безопасность -> Универсальный доступ) у процесса,
который постит события (в готовом приложении — у GigaAM.app).
Чтение буфера обмена на macOS 15+ может показать баннер «N вставил(и) из M»
— это нормальное поведение приватности, не ошибка.

Окно/фокус: модуль НЕ управляет фокусом — он шлёт Cmd+V туда, где фокус
сейчас. Держать фокус у нужного окна — задача вызывающего кода.
"""

from __future__ import annotations

import os
import time

# --- pyobjc: импортируем сразу, но мягко (пакеты уже в venv) ---
try:
    from AppKit import NSData, NSPasteboard, NSPasteboardItem, NSPasteboardTypeString, NSWorkspace
    import Quartz

    _PYOBJC_OK = True
    _IMPORT_ERROR = None
except Exception as _e:  # pragma: no cover — на целевой машине не должно случаться
    _PYOBJC_OK = False
    _IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

KEYCODE_V = 9  # kVK_ANSI_V — физическая клавиша 'v', работает при любой раскладке
kCGEventFlagMaskCommand = Quartz.kCGEventFlagMaskCommand if _PYOBJC_OK else 1 << 20
kCGHIDEventTap = Quartz.kCGHIDEventTap if _PYOBJC_OK else 0


def _result(ok: bool, method: str, error=None) -> dict:
    """Единый формат ответа всех функций модуля."""
    return {"ok": bool(ok), "method": method, "error": error}


def _frontmost_app() -> dict | None:
    """Какое приложение сейчас на переднем плане: {"pid", "name"} | None."""
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        return {"pid": int(app.processIdentifier()),
                "name": app.localizedName() or ""}
    except Exception:
        return None


def check_accessibility(prompt: bool = False) -> bool:
    """Есть ли у текущего процесса право Accessibility (постить события).

    prompt=True — показать системный диалог с просьбой выдать право.
    """
    if not _PYOBJC_OK:
        return False
    try:
        from ApplicationServices import (  # именно отсюда, из Quartz этого нет
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
        from Foundation import NSDictionary

        opts = NSDictionary.dictionaryWithObject_forKey_(True, kAXTrustedCheckOptionPrompt) if prompt else None
        return bool(AXIsProcessTrustedWithOptions(opts))
    except Exception:
        try:
            from ApplicationServices import AXIsProcessTrusted

            return bool(AXIsProcessTrusted())
        except Exception:
            return False


# --------------------------------------------------------------------------
# Буфер обмена
# --------------------------------------------------------------------------

def _save_pasteboard(pb) -> list | None:
    """Снимок ВСЕГО буфера (все элементы, все типы, сырые байты).

    Возвращает list[dict[type -> bytes]] или None, если снять не удалось.
    Снимаем сырые данные, а не живые NSPasteboardItem: после clearContents()
    старые элементы pasteboard становятся невалидными.
    """
    try:
        snapshot: list = []
        for item in pb.pasteboardItems():
            entry = {}
            for t in item.types():
                data = item.dataForType_(t)
                if data is not None:
                    entry[str(t)] = bytes(data)
            if entry:
                snapshot.append(entry)
        return snapshot
    except Exception:
        return None


def _restore_pasteboard(pb, snapshot: list | None) -> bool:
    """Вернуть буфер к снимку. False — если восстановить не удалось."""
    if snapshot is None:
        return False
    try:
        pb.clearContents()
        for entry in snapshot:
            item = NSPasteboardItem.alloc().init()
            for t, raw in entry.items():
                nsdata = NSData.dataWithBytes_length_(raw, len(raw))
                item.setData_forType_(nsdata, t)
            pb.writeObjects_([item])
        return True
    except Exception:
        return False


def _put_text_to_pasteboard(pb, text: str) -> bool:
    try:
        pb.clearContents()
        return bool(pb.setString_forType_(text, NSPasteboardTypeString))
    except Exception:
        return False


# --------------------------------------------------------------------------
# Синтез клавиш
# --------------------------------------------------------------------------

def _post_cmd_v() -> None:
    """Cmd+V: keyDown + keyUp с cmd-флагом на обоих событиях, в kCGHIDEventTap."""
    for is_down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, KEYCODE_V, is_down)
        Quartz.CGEventSetFlags(ev, kCGEventFlagMaskCommand)
        Quartz.CGEventPost(kCGHIDEventTap, ev)
        if is_down:
            time.sleep(0.02)  # пауза down->up: некоторые приложения не ловят мгновенную пару


# --------------------------------------------------------------------------
# Публичный API
# --------------------------------------------------------------------------

def insert_text(text: str, keep_clipboard: bool = True, paste_delay: float = 0.35) -> dict:
    """Вставить текст в приложение с фокусом, как будто нажали Cmd+V.

    keep_clipboard=True  — прежний буфер сохраняется и возвращается на место
                           через paste_delay секунд (буфер на это время
                           подменяется нашим текстом).
    paste_delay          — сколько ждать между Cmd+V и восстановлением буфера.
                           Слишком мало -> целевое приложение может успеть
                           вставить СТАРЫЙ буфер; слишком много -> окно, в
                           котором пользователь успел нажать Cmd+V руками,
                           вставит наш текст.
    """
    if not isinstance(text, str) or not text:
        return _result(False, "clipboard", "пустой или нестроковый text")
    if not _PYOBJC_OK:
        return _result(False, "clipboard", f"pyobjc недоступен: {_IMPORT_ERROR}")

    try:
        target = _frontmost_app()
        if target and target.get("pid") == os.getpid():
            # фокус на самом GigaAM (история/словарь) — вставлять некуда
            return _result(False, "clipboard", "фокус на окне GigaAM")

        pb = NSPasteboard.generalPasteboard()

        snapshot = _save_pasteboard(pb) if keep_clipboard else None

        if not _put_text_to_pasteboard(pb, text):
            return _result(False, "clipboard", "не удалось записать текст в буфер обмена")

        _post_cmd_v()
        time.sleep(paste_delay)

        restored = None
        if keep_clipboard:
            restored = _restore_pasteboard(pb, snapshot)

        result = _result(True, "clipboard")
        if target:
            result["app"] = target.get("name")
        if keep_clipboard and restored is False:
            # вставка сработала, но прежний буфер вернуть не смогли — не крашимся,
            # просто честно сообщаем
            result["error"] = "вставка выполнена, но восстановить прежний буфер не удалось"
        return result
    except Exception as e:
        return _result(False, "clipboard", f"{type(e).__name__}: {e}")


def type_text(text: str) -> dict:
    """Резервный путь: текст одним событием CGEventKeyboardSetUnicodeString.

    Буфер обмена не трогается.

    ⚠️ ПРОВЕРЕНО ЭКСПЕРИМЕНТОМ (TexteEdit, macOS 26.4, активная русская
    раскладка): события с unicode-string НЕ ВСТАВЛЯЮТСЯ — приложение
    игнорирует приложенную строку, потому что keyDown обрабатывает input
    method по текущей раскладке. Plain-клавиши при этом доходят (печатают
    «по раскладке»), а Cmd+V работает всегда (меню-шорткат идёт мимо IM).
    Вывод: на не-латинских раскладках полагаться на этот путь НЕЛЬЗЯ —
    используйте insert_text(). Событие при этом уходит без ошибок, поэтому
    {"ok": True} здесь означает «событие отправлено», а не «текст вставлен».
    """
    if not isinstance(text, str) or not text:
        return _result(False, "typing", "пустой или нестроковый text")
    if not _PYOBJC_OK:
        return _result(False, "typing", f"pyobjc недоступен: {_IMPORT_ERROR}")

    try:
        results = []
        for is_down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, 0, is_down)  # keycode-заглушка 0
            Quartz.CGEventKeyboardSetUnicodeString(ev, len(text), text)
            Quartz.CGEventPost(kCGHIDEventTap, ev)
            results.append(True)
            if is_down:
                time.sleep(0.02)
        return _result(all(results), "typing")
    except Exception as e:
        return _result(False, "typing", f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    # Быстрая самопроверка окружения без вставки
    print("pyobjc:", "OK" if _PYOBJC_OK else _IMPORT_ERROR)
    print("accessibility:", check_accessibility())
