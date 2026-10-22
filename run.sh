#!/bin/zsh
# Запуск тулзы без бандла (для отладки).
cd "$(dirname "$0")"
exec .venv/bin/python app/main.py "$@"
