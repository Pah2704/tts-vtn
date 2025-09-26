#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

TARGET_DIR="models"
VOICES=()
FORCE=0
DOWNLOAD_JSON=1
BASE_URL=""
PATH_PREFIX=""

log() { printf '[download-models] %s\n' "$*" >&2; }
die() { printf '[download-models][ERROR] %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }

usage() {
  printf '%s\n' \
    "Piper model downloader" \
    "" \
    "Options:" \
    "  -d, --dir <DIR>        Target directory (default: models)" \
    "  -v, --voice <ID>       Voice ID (repeatable), e.g. en_GB-alan-medium" \
    "      --base <URL>       Base URL (default: rhasspy/piper-voices)" \
    "      --path <PREFIX>    Path under base, e.g. en/en_GB/alan/medium" \
    "  -f, --force            Re-download even if file exists" \
    "      --no-json          Skip downloading the .onnx.json sidecar" \
    "  -h, --help             Show this help" \
    "" \
    "Examples:" \
    "  scripts/download-models.sh" \
    "  scripts/download-models.sh -d models -v en_GB-alan-medium -v en_US-amy-low" \
    "  scripts/download-models.sh --path en/en_GB/alan/medium -v en_GB-alan-medium"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--dir) TARGET_DIR="${2:-}"; shift 2 ;;
    -v|--voice) VOICES+=("${2:-}"); shift 2 ;;
    --base) BASE_URL="${2:-}"; shift 2 ;;
    --path) PATH_PREFIX="${2:-}"; shift 2 ;;
    -f|--force) FORCE=1; shift ;;
    --no-json) DOWNLOAD_JSON=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1";;
  esac
done

if [[ ${#VOICES[@]} -eq 0 ]]; then
  VOICES=("en_GB-alan-medium")
fi
: "${BASE_URL:=https://huggingface.co/rhasspy/piper-voices/resolve/main}"

need_cmd curl
mkdir -p "$TARGET_DIR"

infer_path_prefix() {
  local voice="$1"
  if [[ -n "$PATH_PREFIX" ]]; then
    printf '%s' "$PATH_PREFIX"; return 0
  fi
  if [[ "$voice" =~ ^([a-z]{2}_[A-Z]{2})-([a-z0-9]+)-([a-z0-9]+)$ ]]; then
    local locale="${BASH_REMATCH[1]}"
    local name="${BASH_REMATCH[2]}"
    local size="${BASH_REMATCH[3]}"
    local lang="${locale%%_*}"
    printf '%s/%s/%s/%s' "$lang" "$locale" "$name" "$size"
  else
    die "Cannot infer path for voice '$voice'. Provide --path."
  fi
}

download_file() {
  local url="$1" dest="$2"
  local tmp; tmp="$(mktemp -p "${TMPDIR:-/tmp}" piper-dl.XXXXXX)"
  curl -fL --retry 3 --retry-connrefused --retry-delay 2 \
       --connect-timeout 20 --max-time 600 -o "$tmp" "$url" || {
    rm -f "$tmp"; die "Failed to download: $url"; }
  [[ -s "$tmp" ]] || { rm -f "$tmp"; die "Downloaded empty file: $url"; }
  mkdir -p "$(dirname "$dest")"; mv -f "$tmp" "$dest"
}

ensure_one_artifact() {
  local voice="$1" ext="$2"
  local prefix url dest
  prefix="$(infer_path_prefix "$voice")"
  url="${BASE_URL%/}/${prefix}/${voice}.${ext}"
  dest="${TARGET_DIR%/}/${voice}.${ext}"

  if [[ $FORCE -eq 1 || ! -f "$dest" || ! -s "$dest" ]]; then
    log "Downloading ${voice}.${ext} ..."
    download_file "$url?download=1" "$dest"
    if [[ "$ext" == "onnx.json" ]] && command -v jq >/dev/null 2>&1; then
      jq -e . "$dest" >/dev/null 2>&1 || { rm -f "$dest"; die "Invalid JSON for ${voice}.${ext}"; }
    fi
  else
    log "${voice}.${ext} already present"
  fi
}

ensure_voice() {
  local voice="$1"
  ensure_one_artifact "$voice" "onnx"
  [[ $DOWNLOAD_JSON -eq 1 ]] && ensure_one_artifact "$voice" "onnx.json"
}

for v in "${VOICES[@]}"; do ensure_voice "$v"; done
log "Models available in ${TARGET_DIR}/"
