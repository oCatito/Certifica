#!/usr/bin/env bash
# Gera dist/Certifica.app (rodar no macOS).
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements-dev.txt

.venv/bin/python -m PyInstaller --noconfirm --clean --windowed \
  --name "Certifica" \
  --icon assets/icon.icns \
  --add-data "assets:assets" \
  --collect-data customtkinter \
  --hidden-import keyring.backends.macOS \
  --osx-bundle-identifier app.certifica.desktop \
  main.py

echo
echo "Pronto: dist/Certifica.app"
