#!/usr/bin/env bash
set -euo pipefail

pyinstaller --windowed --name GradeAudit --collect-all PySide6 --add-data "data:data" desktop.py
