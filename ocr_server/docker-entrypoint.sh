#!/bin/sh
# ============================================================
# Fix cache ownership, then drop privileges.
#
# A volume mounted at $HF_HOME (a host bind mount, or a RunPod network
# volume) replaces the image's directory *including its ownership*, so
# the build-time chown does not survive. Without this the non-root
# service cannot write the model cache and startup fails with EACCES.
# ============================================================
set -e

: "${HF_HOME:=/models}"
: "${HF_HUB_CACHE:=${HF_HOME}/hub}"

mkdir -p "$HF_HUB_CACHE"

if [ "$(id -u)" = "0" ]; then
    # Metadata-only; runs at container start, not per request.
    chown -R ocr:ocr "$HF_HOME" 2>/dev/null || true
    exec runuser -u ocr -- "$@"
fi

# Already non-root (e.g. the platform forced --user): run as-is.
exec "$@"
