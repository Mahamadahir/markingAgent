#!/usr/bin/env bash
set -euo pipefail

pyinstaller \
  --noconfirm \
  --windowed \
  --name GradeAudit \
  --add-data "data:data" \
  --hidden-import PySide6.QtCore \
  --hidden-import PySide6.QtGui \
  --hidden-import PySide6.QtWidgets \
  desktop.py
