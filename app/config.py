"""Константы и пути приложения «GigaAM Диктовка»."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "GigaAM Диктовка"
ORG_NAME = "gigaam-dictation"

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.path.expanduser("~/Library/Application Support/GigaAM-Dictation"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "history.db"

# --- Модель ---------------------------------------------------------------
# Варианты: v3_e2e_ctc (пунктуация, быстрый), v3_e2e_rnnt, v3_ctc, v3_rnnt,
# v2_ctc, v2_rnnt. Чекпойнт качается один раз в ~/.cache/gigaam
MODEL_NAME = os.environ.get("GIGAAM_MODEL", "v3_e2e_ctc")
# "auto" = попробовать MPS (видеочип Мака), не выйдет — CPU
DEVICE = os.environ.get("GIGAAM_DEVICE", "auto")

# --- Поведение -------------------------------------------------------------
MAX_RECORD_SEC = 5 * 60      # дольше 5 минут запись сама остановится
MIN_RECORD_SEC = 0.5         # короче — случайное нажатие, отменяем

# --- Тайминги интерфейса ---------------------------------------------------
CARD_LINGER_SEC = 6.0        # сколько висит карточка с результатом
FADE_MSEC = 280              # скорость появления/исчезания
HINT_DELAY_SEC = 1.2         # подсказка «Esc — отмена» появляется не сразу
