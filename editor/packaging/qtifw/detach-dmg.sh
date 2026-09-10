#!/usr/bin/env bash
set -euo pipefail
mount_point=${1:?usage: detach-dmg.sh MOUNT_POINT}
# Spotlight/diskimages-helper can briefly retain an already-consumed read-only DMG.
for attempt in 1 2 3; do
  if hdiutil detach "$mount_point"; then
    exit 0
  fi
  sleep "$attempt"
done
if ! hdiutil detach -force "$mount_point"; then
  # Only cleanup failed. The caller independently verifies the installed tools.
  printf '%s\n' "::warning::Could not detach temporary Qt IFW image: $mount_point" >&2
fi
