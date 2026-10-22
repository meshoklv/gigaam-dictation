"""test_inserter.py — честная проверка inserter.insert_text на TextEdit.

Ход: создать временный txt -> открыть в TextEdit (временный файл выбран,
потому что при пустом старте TextEdit показывает модальную панель
«Новый документ», и `make new document` по Apple Events может виснуть) ->
вставить строку через insert_text -> прочитать текст документа обратно
через AppleScript -> сравнить -> закрыть TextEdit без сохранения -> удалить
временный файл. Заодно проверяется восстановление буфера обмена.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inserter import check_accessibility, insert_text  # noqa: E402

TEXT = "Проверка вставки 123"


def run(cmd: str, timeout: float = 10.0) -> tuple[int, str]:
    """Запустить команду, вернуть (код, вывод). Ничего не бросает."""
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip() or (p.stderr or "").strip()
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def osascript(script: str, timeout: float = 10.0) -> tuple[int, str]:
    return run(f"osascript -e {shell_quote(script)}", timeout)


def shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _pasteboard_change_count() -> int:
    """changeCount буфера: растёт при каждой перезаписи (нужен, чтобы
    доказать, что restore реально происходил, а не «строка похожа»)."""
    try:
        from AppKit import NSPasteboard

        return int(NSPasteboard.generalPasteboard().changeCount())
    except Exception:
        return -1


def main() -> int:
    print("=== test_inserter ===")
    ax = check_accessibility(prompt=False)
    print(f"Accessibility у процесса-родителя: {ax}")

    # Текущий буфер — чтобы проверить восстановление после вставки
    rc_cb_before, before_cb = osascript("the clipboard as text")
    cc_before = _pasteboard_change_count()
    print(f"Буфер ДО: rc={rc_cb_before}, {before_cb[:60]!r}, changeCount={cc_before}")

    tmp_path = None
    opened = False
    try:
        # Временный файл вместо make new document: нет гонки с панелью открытия
        fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="spike_inserter_")
        with os.fdopen(fd, "w") as f:
            f.write("")

        rc, out = run(f"open -a TextEdit {shell_quote(tmp_path)}")
        if rc != 0:
            print(f"FAIL: не удалось открыть TextEdit с файлом: {out}")
            return 1
        opened = True
        print("TextEdit открыт с временным документом, жду 2 c...")
        time.sleep(2.0)

        # Убедиться, что документ открыт и фокус там (Д7: читаем состояние)
        rc, doc_count = osascript('tell application "TextEdit" to count documents')
        rc2, name = osascript("tell application \"TextEdit\" to get name of front document")
        print(f"Документов в TextEdit: {doc_count!r}, передний: {name!r}, фокус должен быть у TextEdit")
        if rc != 0 or doc_count.strip() == "0":
            print("FAIL: документ не открылся")
            return 1

        # --- сама вставка ---
        res = insert_text(TEXT)
        print(f"insert_text -> {res}")
        time.sleep(1.0)

        # --- читаем документ обратно (независимый источник, Д7) ---
        rc, doc_text = osascript('tell application "TextEdit" to get text of front document')
        if rc != 0:
            print(f"FAIL: не удалось прочитать документ: {doc_text}")
            return 1
        print(f"Текст документа: {doc_text!r}")

        pasted_ok = (doc_text == TEXT)
        print("ПОЛУЧИЛОСЬ" if pasted_ok else "НЕ ПОЛУЧИЛОСЬ",
              f"(ожидание {TEXT!r}, факт {doc_text!r})")

        # --- проверка восстановления буфера ---
        rc_cb_after, after_cb = osascript("the clipboard as text")
        cc_after = _pasteboard_change_count()
        same = (rc_cb_before == rc_cb_after == 0) and (after_cb == before_cb)
        print(f"Буфер ПОСЛЕ: rc={rc_cb_after}, {after_cb[:60]!r}, changeCount={cc_after}")
        print(f"Строки буфера совпали (ДО==ПОСЛЕ): {same}; "
              f"changeCount вырос (restore реально перезаписывал буфер): {cc_after > cc_before}")

        return 0 if pasted_ok else 1
    finally:
        if opened:
            rc, out = osascript('tell application "TextEdit" to quit saving no', timeout=8.0)
            print(f"TextEdit закрыт без сохранения (rc={rc} {out})")
            time.sleep(0.5)
            rc, out = run("pgrep -x TextEdit")
            if rc == 0:
                print("TextEdit ещё жив, добиваю SIGTERM")
                run("pkill -x TextEdit")
                time.sleep(0.5)
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        print("Временный файл удалён, окон TextEdit не оставлено" if run("pgrep -x TextEdit")[0] != 0
              else "ВНИМАНИЕ: TextEdit всё ещё жив")


if __name__ == "__main__":
    sys.exit(main())
