#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Ошибка: macOS-сборку нужно запускать на macOS." >&2
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Ошибка: не найден .venv/bin/python. Создай/активируй виртуальное окружение проекта." >&2
  exit 1
fi

.venv/bin/python -m pip install -r requirements-build.txt
rm -rf build dist
.venv/bin/python -m PyInstaller --noconfirm --clean PersonnelTracker.spec

echo
echo "Сборка завершена:"
echo "$ROOT_DIR/dist/PersonnelTracker.app"
