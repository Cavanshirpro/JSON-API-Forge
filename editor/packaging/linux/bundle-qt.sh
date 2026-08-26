#!/usr/bin/env bash
set -euo pipefail

stage=${1:?usage: bundle-qt.sh STAGE_DIRECTORY}
exe="$stage/bin/JSON-API-Forge-Editor"
test -x "$exe"

query_tool=""
for candidate in qtpaths6 qtpaths; do
  if command -v "$candidate" >/dev/null 2>&1; then
    query_tool=$candidate
    break
  fi
done
test -n "$query_tool"

qt_query() {
  "$query_tool" --query "$1"
}

plugins=$(qt_query QT_INSTALL_PLUGINS)
data=$(qt_query QT_INSTALL_DATA)
translations=$(qt_query QT_INSTALL_TRANSLATIONS)
libexecs=$(qt_query QT_INSTALL_LIBEXECS)

mkdir -p "$stage/lib" "$stage/plugins" "$stage/resources" "$stage/translations" "$stage/libexec"

for directory in platforms imageformats iconengines platformthemes xcbglintegrations tls; do
  if [[ -d "$plugins/$directory" ]]; then
    cp -aL "$plugins/$directory" "$stage/plugins/"
  fi
done

if [[ -d "$data/resources" ]]; then
  find "$data/resources" -maxdepth 1 -type f \
    \( -name '*.pak' -o -name '*.bin' -o -name 'icudtl.dat' \) \
    -exec cp -L {} "$stage/resources/" \;
fi
if [[ -d "$translations/qtwebengine_locales" ]]; then
  cp -aL "$translations/qtwebengine_locales" "$stage/translations/"
fi
if [[ -x "$libexecs/QtWebEngineProcess" ]]; then
  cp -L "$libexecs/QtWebEngineProcess" "$stage/libexec/"
  chmod 0755 "$stage/libexec/QtWebEngineProcess"
fi

copy_dependencies() {
  local binary=$1
  ldd "$binary" | awk '
    /=> \/.*\(/ { print $3 }
    /^[[:space:]]*\/.*\(/ { print $1 }
  ' | while IFS= read -r library; do
    case "$(basename "$library")" in
      libQt6*|libicu*|libxkbcommon*|libpcre2-16*|libdouble-conversion*|libmd4c*|libb2*)
        cp -L "$library" "$stage/lib/$(basename "$library")"
        ;;
    esac
  done
}

copy_dependencies "$exe"
if [[ -x "$stage/libexec/QtWebEngineProcess" ]]; then
  copy_dependencies "$stage/libexec/QtWebEngineProcess"
fi
while IFS= read -r binary; do
  copy_dependencies "$binary"
done < <(find "$stage/plugins" -type f -name '*.so')
while IFS= read -r library; do
  copy_dependencies "$library"
done < <(find "$stage/lib" -maxdepth 1 -type f -name '*.so*')

test -f "$stage/lib/libQt6Core.so.6"
test -f "$stage/plugins/platforms/libqxcb.so"
