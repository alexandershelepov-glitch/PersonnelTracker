#!/bin/bash
set -u
cd "$(dirname "$0")"

# Сохраняем вывод запуска: при двойном щелчке окно Terminal может закрыться
# до того, как сообщение об ошибке будет скопировано.
LOG_DIR="data/logs"
LOG_FILE="$LOG_DIR/launch.log"
mkdir -p "$LOG_DIR"

log() {
  echo "$*" | tee -a "$LOG_FILE"
}

run_logged() {
  "$@" 2>&1 | tee -a "$LOG_FILE"
  return "${PIPESTATUS[0]}"
}

log ""
log "[$(date '+%Y-%m-%d %H:%M:%S')] Запуск приложения"
log "Журнал запуска: $LOG_FILE"

if ! command -v python3 >/dev/null 2>&1; then
  log "ОШИБКА: не найден Python 3. Установите Python с https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d ".venv" ]; then
  if ! python3 -m venv .venv; then
    log "ОШИБКА: не удалось создать виртуальное окружение Python."
    exit 1
  fi
fi

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  log "ОШИБКА: виртуальное окружение повреждено: $PYTHON не найден."
  exit 1
fi

if ! run_logged "$PYTHON" -m pip install --disable-pip-version-check -r requirements.txt; then
  log "ОШИБКА: не удалось установить зависимости. Проверьте подключение к интернету и повторите запуск."
  exit 1
fi

# PySide6 содержит Cocoa-плагин, но в некоторых окружениях macOS Qt не
# определяет его путь автоматически. Передаём путь явно.
QT_PLUGINS_DIR="$($PYTHON -c 'from PySide6.QtCore import QLibraryInfo; print(QLibraryInfo.path(QLibraryInfo.PluginsPath))')"
QT_COCOA_PLUGIN="$QT_PLUGINS_DIR/platforms/libqcocoa.dylib"
if [ ! -f "$QT_COCOA_PLUGIN" ]; then
  log "ОШИБКА: не найден Qt Cocoa-плагин: $QT_COCOA_PLUGIN"
  exit 1
fi
unset QT_PLUGIN_PATH
export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGINS_DIR/platforms"

run_logged "$PYTHON" app.py
exit $?
