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

APP_PATH="$ROOT_DIR/dist/PersonnelTracker.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Ошибка: PyInstaller завершился, но приложение не найдено: $APP_PATH" >&2
  exit 1
fi

# iCloud/Finder can attach resource-fork and FinderInfo xattrs to files inside
# the bundle. They make macOS codesign reject an otherwise valid local build.
/usr/bin/xattr -cr "$APP_PATH"
/usr/bin/codesign --force --deep --sign - "$APP_PATH"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo
echo "Сборка завершена и локальная подпись проверена:"
echo "$APP_PATH"
