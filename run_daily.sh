#!/bin/bash
# Daily AI Pipeline runner for macOS
# Usage: ./run_daily.sh [--send-email|--no-email]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DATE_STR=$(date +%Y%m%d)
LOG_DIR="$SCRIPT_DIR/logs"
OUTPUT_DIR="$SCRIPT_DIR/outputs"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

SEND_FLAG=""
# Auto-detect: send email if EMAIL_PASSWORD is set
if grep -q "^EMAIL_PASSWORD=" .env 2>/dev/null && grep -v "^#" .env | grep -q "^EMAIL_PASSWORD=."; then
    SEND_FLAG="--send-email"
else
    SEND_FLAG="--no-email"
fi

# Override from CLI args
for arg in "$@"; do
    case "$arg" in
        --send-email) SEND_FLAG="--send-email" ;;
        --no-email)   SEND_FLAG="--no-email" ;;
        --date=*)     DATE_ARG="$arg" ;;
    esac
done

echo "[$(date)] Starting daily pipeline $DATE_STR" | tee -a "$LOG_DIR/runner_$DATE_STR.log"

# Activate venv if exists
if [ -d .venv ]; then
    source .venv/bin/activate
fi

python3 daily_pipeline.py $SEND_FLAG ${DATE_ARG:-} 2>&1 | tee -a "$LOG_DIR/runner_$DATE_STR.log"

EXIT_CODE=${PIPESTATUS[0]}
echo "[$(date)] Pipeline finished with exit code $EXIT_CODE" | tee -a "$LOG_DIR/runner_$DATE_STR.log"
exit $EXIT_CODE
