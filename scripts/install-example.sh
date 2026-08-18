#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <TaskBoard|GuildLedger|RealtimeSupport|MediaLibrary|PublicCatalog> [destination-app-directory]" >&2
  exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository_root=$(cd -- "$script_dir/.." && pwd)
name=$1
destination_root=${2:-"$repository_root/app"}
source_dir="$repository_root/app/$name"
target_dir="$destination_root/$name"

if [[ ! -f "$source_dir/app.json" ]]; then
  echo "Unknown example: $name" >&2
  exit 2
fi
if [[ -e "$target_dir" ]]; then
  echo "Refusing to overwrite existing target: $target_dir" >&2
  exit 1
fi

mkdir -p -- "$destination_root"
cp -R -- "$source_dir" "$target_dir"
echo "Installed $name at $target_dir"
echo "Next: run 'forge init', 'forge validate', and 'forge dev' in the destination checkout."
