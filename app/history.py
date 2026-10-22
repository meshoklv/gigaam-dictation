"""История + настройки: двухтабный центр тулзы.

Открывается кликом по карточке результата, по значку в меню-баре или из меню.
Вкладка «История» — поиск, копирование, повторная вставка, удаление.
Вкладка «Настройки» — вставка, буфер, автозапуск, словарь, права, о модели.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)


def human_time(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    now = datetime.now()
    hm = dt.strftime("%H:%M")
    if dt.date() == now.date():
        return f"сегодня {hm}"
    if dt.date() == (now - timedelta(days=1)).date():
        return f"вчера {hm}"
    months = ["янв", "фев", "мар", "апр", "мая", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]
    if dt.year == now.year:
        return f"{dt.day} {months[dt.month - 1]} {hm}"
    return f"{dt.day}.{dt.month:02d}.{dt.year} {hm}"


def human_dur(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def plural_records(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} запись"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} записи"
    return f"{n} записей"


class HistoryStore(QObject):
    def __init__(self, path) -> None:
        super().__init__()
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS transcriptions ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts REAL NOT NULL, dur REAL NOT NULL, text TEXT NOT NULL)"
        )
        self._db.commit()

    def add(self, text: str, dur: float) -> int:
        cur = self._db.execute(
            "INSERT INTO transcriptions (ts, dur, text) VALUES (?,?,?)",
            (time.time(), dur, text),
        )
        self._db.commit()
        return int(cur.lastrowid)

    def recent(self, query: str | None = None, limit: int = 300) -> list[dict]:
        if not query:
            rows = self._db.execute(
                "SELECT id, ts, dur, text FROM transcriptions "
                "ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
            return [{"id": r[0], "ts": r[1], "dur": r[2], "text": r[3]} for r in rows]
        # LIKE в SQLite не сворачивает регистр кириллицы — ищем по-питоновски
        rows = self._db.execute(
            "SELECT id, ts, dur, text FROM transcriptions ORDER BY id DESC LIMIT 2000"
        ).fetchall()
        q = query.lower()
        out = []
        for r in rows:
            if q in r[3].lower():
                out.append({"id": r[0], "ts": r[1], "dur": r[2], "text": r[3]})
                if len(out) >= limit:
                    break
        return out

    def delete(self, row_id: int) -> None:
        self._db.execute("DELETE FROM transcriptions WHERE id=?", (row_id,))
        self._db.commit()

    def clear(self) -> None:
        self._db.execute("DELETE FROM transcriptions")
        self._db.commit()

    def count(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0])


QSS = """
QWidget { background: #16161b; }
#Root { background: #16161b; }
#Title { color: #f5f5f7; font-size: 17px; font-weight: 600; }
#Count { color: #8e8e98; font-size: 12px; }
QTabWidget::pane { border: none; }
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: #8e8e98; padding: 9px 20px;
               font-size: 13px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ff7a59; border-bottom: 2px solid #ff7a59; }
QTabBar::tab:hover:!selected { color: #c9c9d1; }
QLineEdit {
  background: #232329; color: #f5f5f7; border: 1px solid #2e2e36;
  border-radius: 10px; padding: 8px 12px; font-size: 13px;
}
QLineEdit:focus { border-color: #ff7a59; }
QScrollArea { border: none; background: transparent; }
#Row { background: transparent; border-radius: 12px; }
#Row:hover { background: #232329; }
#RowText { color: #e8e8ec; font-size: 13px; line-height: 1.35; }
#RowTime { color: #8e8e98; font-size: 11px; }
#RowDur { color: #6e6e78; font-size: 11px; background: #232329;
          border-radius: 6px; padding: 1px 6px; }
QPushButton#Mini {
  color: #c9c9d1; background: #2b2b33; border: none; border-radius: 8px;
  padding: 4px 10px; font-size: 11px;
}
QPushButton#Mini:hover { background: #3a3a44; color: #ffffff; }
QPushButton#Mini#Del:hover { background: #4b2a2a; color: #ff8a80; }
#ClearBtn { color: #b46b6b; background: transparent; border: none;
            font-size: 12px; padding: 6px; text-align: left; }
#ClearBtn:hover { color: #ff8a80; }
#Empty { color: #6e6e78; font-size: 13px; }
#Hint { color: #55555e; font-size: 11px; }
#SettingsTitle { color: #8e8e98; font-size: 11px; letter-spacing: 1px; }
QCheckBox { color: #e8e8ec; font-size: 13px; spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px;
  border: 1px solid #3a3a44; background: #232329; }
QCheckBox::indicator:checked { background: #ff7a59; border-color: #ff7a59; }
QCheckBox:disabled { color: #55555e; }
QPushButton#Big {
  color: #e8e8ec; background: #2b2b33; border: none; border-radius: 10px;
  padding: 9px 16px; font-size: 13px; text-align: center;
}
QPushButton#Big:hover { background: #3a3a44; }
#InfoLabel { color: #6e6e78; font-size: 11px; }
#Sep { color: #2e2e36; }
"""


class RowWidget(QFrame):
    insertRequested = Signal(str)
    deleted = Signal(int)

    def __init__(self, row: dict) -> None:
        super().__init__()
        self.row_id = row["id"]
        self.text = row["text"]
        self.setObjectName("Row")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        t_lbl = QLabel(human_time(row["ts"]))
        t_lbl.setObjectName("RowTime")
        d_lbl = QLabel(human_dur(row["dur"]))
        d_lbl.setObjectName("RowDur")
        top.addWidget(t_lbl)
        top.addWidget(d_lbl)
        top.addStretch(1)

        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(6)
        for label, cb in (
            ("Вставить", self._insert),
            ("Копировать", self._copy),
            ("✕", self._delete),
        ):
            b = QPushButton(label)
            b.setObjectName("Del" if label == "✕" else "Mini")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(cb)
            self.buttons.addWidget(b)
        top.addLayout(self.buttons)
        v.addLayout(top)

        body = QLabel(row["text"])
        body.setObjectName("RowText")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setCursor(Qt.CursorShape.IBeamCursor)
        v.addWidget(body)
        self._show_buttons(False)

    def _show_buttons(self, on: bool) -> None:
        for i in range(self.buttons.count()):
            w = self.buttons.itemAt(i).widget()
            if w is not None:
                w.setVisible(on)

    def enterEvent(self, a0) -> None:
        self._show_buttons(True)
        super().enterEvent(a0)

    def leaveEvent(self, a0) -> None:
        self._show_buttons(False)
        super().leaveEvent(a0)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.text)

    def _insert(self) -> None:
        self.insertRequested.emit(self.text)

    def _delete(self) -> None:
        self.deleted.emit(self.row_id)


class HistoryWindow(QWidget):
    insertRequested = Signal(str)

    TAB_HISTORY, TAB_SETTINGS = 0, 1

    def __init__(self, store: HistoryStore, controller=None) -> None:
        super().__init__()
        self.store = store
        self.controller = controller
        self.prev_app: dict | None = None  # приложение, активное до открытия окна
        self.setWindowTitle("GigaAM · История и настройки")
        self.resize(520, 640)
        self.setStyleSheet(QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_history_page(), "История")
        self.tabs.addTab(self._build_settings_page(), "Настройки")
        self.tabs.currentChanged.connect(
            lambda i: self._sync_autostart() if i == self.TAB_SETTINGS else None)
        root.addWidget(self.tabs)

    # --- вкладка «История» -------------------------------------------------
    def _build_history_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        root = QVBoxLayout(page)
        root.setContentsMargins(20, 14, 20, 12)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("История")
        title.setObjectName("Title")
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("Count")
        head.addWidget(title)
        head.addSpacing(8)
        head.addWidget(self.count_lbl)
        head.addStretch(1)
        root.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по всему, что ты наговорил…")
        self.search.textChanged.connect(self._reload)
        root.addWidget(self.search)

        self.listw = QListWidget()
        self.listw.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { margin-bottom: 6px; }")
        self.listw.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        root.addWidget(self.listw, 1)

        foot = QHBoxLayout()
        clear = QPushButton("Очистить всё")
        clear.setObjectName("ClearBtn")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._clear_all)
        foot.addWidget(clear)
        foot.addStretch(1)
        root.addLayout(foot)

        self._reload()
        return page

    def _reload(self) -> None:
        self.listw.clear()
        query = self.search.text().strip() or None
        rows = self.store.recent(query)
        total = self.store.count()
        for r in rows:
            w = RowWidget(r)
            w.insertRequested.connect(self.insertRequested)
            w.deleted.connect(self._delete_row)
            item = QListWidgetItem()
            item.setSizeHint(w.sizeHint())
            self.listw.addItem(item)
            self.listw.setItemWidget(item, w)
        n = len(rows)
        if query or total > n:
            self.count_lbl.setText(f"{plural_records(n)} из {total}")
        else:
            self.count_lbl.setText(plural_records(n))
        if not rows:
            e = QLabel("Пока пусто.\nНажми правую ⌘, наговори — и текст появится здесь.")
            e.setObjectName("Empty")
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item = QListWidgetItem()
            item.setSizeHint(e.sizeHint())
            self.listw.addItem(item)
            self.listw.setItemWidget(item, e)

    def _delete_row(self, row_id: int) -> None:
        self.store.delete(row_id)
        self._reload()

    def _clear_all(self) -> None:
        ret = QMessageBox.question(
            self, "Очистить историю?",
            "Удалить все записи? Отменить это нельзя.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.store.clear()
            self._reload()

    # --- вкладка «Настройки» -------------------------------------------------
    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 20, 24, 16)
        v.setSpacing(12)

        def section(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("SettingsTitle")
            return lbl

        c = self.controller
        insert_on = c.insert_enabled if c else True
        keep_on = c.keep_clipboard if c else True

        v.addWidget(section("ДИКТОВКА"))
        self.chk_insert = QCheckBox("Вставлять текст в приложения")
        self.chk_insert.setChecked(insert_on)
        self.chk_insert.toggled.connect(
            lambda on: c.set_insert(on) if c else None)
        v.addWidget(self.chk_insert)

        self.chk_clip = QCheckBox("Восстанавливать прежний буфер обмена")
        self.chk_clip.setChecked(keep_on)
        self.chk_clip.setEnabled(insert_on)
        self.chk_clip.toggled.connect(
            lambda on: c.set_keep_clipboard(on) if c else None)
        v.addWidget(self.chk_clip)

        self.chk_login = QCheckBox("Запускать при входе в систему")
        self.chk_login.toggled.connect(
            lambda on: c.set_autostart(on) if c else None)
        v.addWidget(self.chk_login)

        v.addSpacing(8)
        sep = QLabel()
        sep.setObjectName("Sep")
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2e2e36; max-height: 1px; border: none;")
        v.addWidget(sep)

        v.addWidget(section("ИНСТРУМЕНТЫ"))
        row = QHBoxLayout()
        row.setSpacing(10)
        btn_dict = QPushButton("Словарь замен…")
        btn_dict.setObjectName("Big")
        btn_dict.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dict.clicked.connect(lambda: c.open_dictionary() if c else None)
        row.addWidget(btn_dict)
        btn_perm = QPushButton("Права и доступы…")
        btn_perm.setObjectName("Big")
        btn_perm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_perm.clicked.connect(lambda: c.open_permissions() if c else None)
        row.addWidget(btn_perm)
        v.addLayout(row)

        v.addStretch(1)
        self.info_lbl = QLabel()
        self.info_lbl.setObjectName("InfoLabel")
        self.info_lbl.setWordWrap(True)
        v.addWidget(self.info_lbl)
        self._refresh_info()
        return page

    def _refresh_info(self) -> None:
        c = self.controller
        engine_info = ""
        if c is not None:
            eng = c.engine.engine
            st = {"ready": "готова", "loading": "прогревается",
                  "error": "ошибка", "init": "прогревается"}.get(eng.state, eng.state)
            engine_info = (f"Модель: {eng.model_name} · {eng.device_used or 'cpu'} · {st}\n")
        self.info_lbl.setText(
            engine_info
            + "Правая ⌘ — диктовка, ещё раз — вставить, Esc — отмена.\n"
              "Данные не покидают этот Мак.")

    # --- открытие ------------------------------------------------------------
    def open_and_focus(self, tab: int = TAB_HISTORY) -> None:
        self._remember_frontmost()
        self._sync_checkboxes()
        if tab == self.TAB_SETTINGS:
            self._sync_autostart()
        self._refresh_info()
        self.tabs.setCurrentIndex(tab)
        self.show()
        self.raise_()
        self.activateWindow()

    def _remember_frontmost(self) -> None:
        """Запомнить, какое приложение было активно до открытия — туда
        уйдёт «Вставить» из истории."""
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is not None:
                self.prev_app = {"pid": int(app.processIdentifier()),
                                 "name": app.localizedName() or ""}
        except Exception:
            pass

    def _sync_checkboxes(self) -> None:
        c = self.controller
        if c is None:
            return
        for chk, val in ((self.chk_insert, c.insert_enabled),
                         (self.chk_clip, c.keep_clipboard)):
            chk.blockSignals(True)
            chk.setChecked(val)
            chk.blockSignals(False)
        self.chk_clip.setEnabled(c.insert_enabled)

    def _sync_autostart(self) -> None:
        """Состояние автозапуска узнаём лениво: запрос к System Events
        может вызвать системный вопрос про «Автоматизацию»."""
        if self.controller is None:
            return
        try:
            from main import is_login_item
            self.chk_login.blockSignals(True)
            self.chk_login.setChecked(is_login_item())
            self.chk_login.blockSignals(False)
        except Exception:
            pass
