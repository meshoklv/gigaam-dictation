"""Словарь замен: «как звучит = как писать».

Распознаватель не знает термины (README.md, API, GitHub...) — словарь чинит
это после распознавания: регистронезависимо заменяет «ридми мд» → «README.md».
Хранится в words.json рядом с историей, правится из окна тулзы.
"""
from __future__ import annotations

import json
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from config import DATA_DIR

WORDS_PATH = DATA_DIR / "words.json"

# Стартовый набор пуст. Примеры правил — в words.example.json в корне репо;
# скопируйте его в ~/Library/Application Support/GigaAM-Dictation/words.json
# (его же делает install.sh) или правьте словарь из окна приложения.
DEFAULT_RULES: list[list[str]] = []


def _replace_ci(text: str, spoken: str, written: str) -> str:
    """Регистронезависимая замена ЦЕЛЫХ слов/фраз (не внутри слова):
    «клод» не тронет «клода», иначе получилось бы «Claudeа»."""
    pattern = re.compile(
        r"(?<![а-яёa-z0-9])" + re.escape(spoken) + r"(?![а-яёa-z0-9])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda _m: written, text)


class Dictionary:
    def __init__(self) -> None:
        self.rules: list[tuple[str, str]] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(WORDS_PATH.read_text(encoding="utf-8"))
            self.rules = [(str(a).strip(), str(b).strip())
                          for a, b in data.get("rules", []) if str(a).strip()]
        except Exception:
            self.rules = []
        if not self.rules and not WORDS_PATH.exists():
            self.rules = [tuple(r) for r in DEFAULT_RULES]
            self.save()

    def save(self) -> None:
        WORDS_PATH.write_text(
            json.dumps({"rules": [list(r) for r in self.rules]},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")

    def apply(self, text: str) -> str:
        # длинные правила первыми: «клод мд» должно сработать раньше «клод»;
        # lambda вместо строки — чтобы бэкслеши в поле «писать» не читались
        # как regex-замена
        for spoken, written in sorted(self.rules, key=lambda r: -len(r[0])):
            if spoken.lower() in text.lower():
                text = _replace_ci(text, spoken.lower(), written)
        return text

    def to_edit_text(self) -> str:
        return "\n".join(f"{a} = {b}" for a, b in self.rules)

    def from_edit_text(self, raw: str) -> int:
        rules = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for sep in (" = ", "=", " → ", "→", "\t"):
                if sep in line:
                    a, b = line.split(sep, 1)
                    if a.strip() and b.strip():
                        rules.append((a.strip(), b.strip()))
                    break
        self.rules = rules
        self.save()
        return len(rules)


class DictionaryWindow(QWidget):
    saved = Signal(int)

    def __init__(self, dictionary: Dictionary) -> None:
        super().__init__()
        self.dictionary = dictionary
        self.setWindowTitle("Словарь замен")
        self.resize(480, 380)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        hint = QLabel(
            "Одна строка — одна замена:  что слышно = что писать\n"
            "Например:  ридми мд = README.md   ·   реалтайм = realtime\n"
            "Регистр не важен. Строки с # — комментарии.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.edit = QPlainTextEdit()
        self.edit.setPlainText(dictionary.to_edit_text())
        self.edit.setStyleSheet(
            "QPlainTextEdit { background:#1d1d23; color:#e8e8ec; border:1px solid #2e2e36;"
            "border-radius:10px; padding:8px; font-size:13px; }")
        v.addWidget(self.edit, 1)

        row = QVBoxLayout()
        btn = QPushButton("Сохранить")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background:#ff7a59; color:#1a1a1f; border:none;"
            "border-radius:10px; padding:8px 18px; font-weight:600; font-size:13px; }"
            "QPushButton:hover { background:#ff8f73; }")
        btn.clicked.connect(self._save)
        row.addWidget(btn)
        v.addLayout(row)

    def _save(self) -> None:
        n = self.dictionary.from_edit_text(self.edit.toPlainText())
        self.saved.emit(n)

    def open_and_focus(self) -> None:
        self.edit.setPlainText(self.dictionary.to_edit_text())
        self.show()
        self.raise_()
        self.activateWindow()
