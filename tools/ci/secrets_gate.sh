#!/usr/bin/env bash
set -euo pipefail
exec python3 "$(dirname "$0")/secret_checks.py" detector "${1:-.}"
