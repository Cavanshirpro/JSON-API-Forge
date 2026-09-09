#!/usr/bin/env bash
set -euo pipefail

launcher=$(readlink -f "$0")
app_root=$(CDPATH= cd -- "$(dirname -- "$launcher")" && pwd)

export LD_LIBRARY_PATH="$app_root/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$app_root/plugins"

if [[ -x "$app_root/libexec/QtWebEngineProcess" ]]; then
  export QTWEBENGINEPROCESS_PATH="$app_root/libexec/QtWebEngineProcess"
fi
if [[ -d "$app_root/resources" ]]; then
  export QTWEBENGINE_RESOURCES_PATH="$app_root/resources"
fi
if [[ -d "$app_root/translations/qtwebengine_locales" ]]; then
  export QTWEBENGINE_LOCALES_PATH="$app_root/translations/qtwebengine_locales"
fi

exec "$app_root/bin/JSON-API-Forge-Editor" "$@"
