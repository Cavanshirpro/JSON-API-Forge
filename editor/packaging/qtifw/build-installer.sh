#!/usr/bin/env bash
set -euo pipefail

stage=${1:?usage: build-installer.sh STAGE_DIRECTORY OUTPUT_FILE linux|macos [BINARYCREATOR]}
output=${2:?usage: build-installer.sh STAGE_DIRECTORY OUTPUT_FILE linux|macos [BINARYCREATOR]}
platform=${3:?usage: build-installer.sh STAGE_DIRECTORY OUTPUT_FILE linux|macos [BINARYCREATOR]}
binarycreator=${4:-binarycreator}

case "$platform" in
  linux|macos) ;;
  *) printf '%s\n' "unsupported Qt IFW platform: $platform" >&2; exit 2 ;;
esac

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
stage=$(CDPATH= cd -- "$stage" && pwd)
output_parent=$(dirname -- "$output")
mkdir -p "$output_parent"
output_parent=$(CDPATH= cd -- "$output_parent" && pwd)
output="$output_parent/$(basename -- "$output")"
binarycreator=$(command -v "$binarycreator")
case "$platform" in
  linux) test -x "$stage/bin/JSON-API-Forge-Editor"; test -x "$stage/json-api-forge-editor" ;;
  macos) test -x "$stage/JSON-API-Forge-Editor.app/Contents/MacOS/JSON-API-Forge-Editor" ;;
esac

work_root=$(mktemp -d)
trap 'rm -rf -- "$work_root"' EXIT
config_root="$work_root/config"
meta_root="$work_root/packages/dev.jsonapiforge.editor/meta"
data_root="$work_root/packages/dev.jsonapiforge.editor/data"
mkdir -p "$config_root" "$meta_root" "$data_root"

cp "$repository_root/editor/packaging/qtifw/config/config-$platform.xml" "$config_root/config.xml"
cp "$repository_root/editor/resources/brand-mark-transparent.png" "$config_root/installer-window-icon.png"
if [[ $platform == linux ]]; then
  cp "$repository_root/editor/resources/logo.png" "$config_root/forge-editor.png"
else
  cp "$repository_root/editor/resources/forge-editor.icns" "$config_root/forge-editor.icns"
fi
cp "$repository_root/editor/packaging/qtifw/packages/dev.jsonapiforge.editor/meta/package.xml" "$meta_root/"
cp "$repository_root/editor/packaging/qtifw/packages/dev.jsonapiforge.editor/meta/installscript.qs" "$meta_root/"
cp "$repository_root/LICENSE" "$meta_root/license.txt"
cp -a "$stage"/. "$data_root/"

"$binarycreator" -f -c "$config_root/config.xml" -p "$work_root/packages" "$output"
test -f "$output"
test "$(wc -c < "$output")" -gt 1000000
