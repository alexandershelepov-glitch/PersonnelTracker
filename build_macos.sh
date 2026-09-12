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

# A fresh build environment needs both the runtime dependency and PyInstaller.
.venv/bin/python -m pip install -r requirements.txt -r requirements-build.txt

# Build outside the repository/iCloud tree. Finder/iCloud metadata such as
# com.apple.FinderInfo or resource forks can make codesign reject a bundle.
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/PersonnelTracker-build.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT
STAGE_BUILD="$STAGE_DIR/build"
STAGE_DIST="$STAGE_DIR/dist"
STAGED_APP="$STAGE_DIST/PersonnelTracker.app"
APP_PATH="$ROOT_DIR/dist/PersonnelTracker.app"

rm -rf build dist
.venv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --workpath "$STAGE_BUILD" \
  --distpath "$STAGE_DIST" \
  PersonnelTracker.spec

if [[ ! -d "$STAGED_APP" ]]; then
  echo "Ошибка: PyInstaller завершился, но приложение не найдено: $STAGED_APP" >&2
  exit 1
fi

# Sign and verify the staging bundle first.
/usr/bin/xattr -cr "$STAGED_APP"
/usr/bin/codesign --force --deep --sign - "$STAGED_APP"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$STAGED_APP"

# Copy without resource forks/extended attributes, then sign and verify the
# actual artifact that remains in dist. This is important when the repository
# itself lives in iCloud Drive.
mkdir -p "$ROOT_DIR/dist"
/usr/bin/ditto --norsrc --noextattr "$STAGED_APP" "$APP_PATH"
/usr/bin/xattr -cr "$APP_PATH"
/usr/bin/codesign --force --deep --sign - "$APP_PATH"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP_PATH"

# Give Finder/iCloud a moment to touch the destination, then verify the final
# bundle once more. If metadata invalidates the signature, the build must fail
# instead of reporting a release-ready artifact.
sleep 1
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo
echo "Сборка завершена; финальная локальная подпись проверена:"
echo "$APP_PATH"
