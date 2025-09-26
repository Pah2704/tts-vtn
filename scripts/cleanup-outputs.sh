#!/usr/bin/env bash
# Clean up generated audio outputs by age or total size.
# Usage:
#   scripts/cleanup-outputs.sh [-d DAYS] [-s MAX_GB] [-n]
# Options:
#   -d DAYS    Remove files older than DAYS.
#   -s MAX_GB  Keep directory under MAX_GB total size (removes oldest first).
#   -n         Dry-run. Print actions without deleting.
# Environment:
#   OUTPUTS_DIR overrides the directory (default backend/outputs).

set -euo pipefail

show_help() {
  grep '^#' "$0" | sed 's/^# \?//'
}

DRY_RUN=0
AGE_DAYS=""
MAX_GB=""

while getopts ":d:s:nh" opt; do
  case "$opt" in
    d) AGE_DAYS="$OPTARG" ;;
    s) MAX_GB="$OPTARG" ;;
    n) DRY_RUN=1 ;;
    h) show_help; exit 0 ;;
    :) echo "Missing value for -$OPTARG" >&2; exit 1 ;;
    \?) echo "Unknown option -$OPTARG" >&2; show_help; exit 1 ;;
  esac
done

OUTPUTS_DIR=${OUTPUTS_DIR:-backend/outputs}
if [[ ! -d "$OUTPUTS_DIR" ]]; then
  echo "Outputs directory '$OUTPUTS_DIR' does not exist. Nothing to do." >&2
  exit 0
fi

if [[ -n "$AGE_DAYS" ]] && ! [[ "$AGE_DAYS" =~ ^[0-9]+$ ]]; then
  echo "DAYS must be integer" >&2
  exit 1
fi

if [[ -n "$MAX_GB" ]] && ! [[ "$MAX_GB" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "MAX_GB must be numeric" >&2
  exit 1
fi

run_rm() {
  local path="$1"
  if (( DRY_RUN )); then
    echo "rm $path"
  else
    rm -f -- "$path"
  fi
}

# Remove files older than AGE_DAYS
if [[ -n "$AGE_DAYS" ]]; then
  echo "Removing files older than $AGE_DAYS days from $OUTPUTS_DIR"
  while IFS= read -r file; do
    run_rm "$file"
    meta="$file.meta.json"
    if [[ -f "$meta" ]]; then
      run_rm "$meta"
    fi
  done < <(find "$OUTPUTS_DIR" -type f -mtime +"$AGE_DAYS" ! -name '*.meta.json')
fi

# Trim to maximum size
if [[ -n "$MAX_GB" ]]; then
  limit_mb=$(python - <<PY
from decimal import Decimal
print(int(Decimal('$MAX_GB') * 1024))
PY
)
  du_output=$(du -sm "$OUTPUTS_DIR" | awk '{print $1}')
  current_mb=${du_output:-0}
  if [[ -z "$current_mb" ]]; then current_mb=0; fi
  if (( current_mb > limit_mb )); then
    echo "Directory size ${current_mb}MB exceeds limit ${limit_mb}MB. Removing oldest files."
    while (( current_mb > limit_mb )); do
      oldest=$(find "$OUTPUTS_DIR" -type f ! -name '*.meta.json' -printf '%T@\t%p\n' | sort -n | head -n 1 | cut -f2-)
      if [[ -z "$oldest" ]]; then
        break
      fi
      run_rm "$oldest"
      meta="$oldest.meta.json"
      if [[ -f "$meta" ]]; then
        run_rm "$meta"
      fi
      du_output=$(du -sm "$OUTPUTS_DIR" | awk '{print $1}')
      current_mb=${du_output:-0}
    done
  fi
fi

echo "Cleanup complete." 
