#!/usr/bin/env sh
set -eu

version="0.5.0"
destination=""
repository="Cavanshirpro/JSON-API-Forge"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      [ "$#" -ge 2 ] || { printf '%s\n' "--version requires a value" >&2; exit 2; }
      version=$2
      shift 2
      ;;
    --destination)
      [ "$#" -ge 2 ] || { printf '%s\n' "--destination requires a value" >&2; exit 2; }
      destination=$2
      shift 2
      ;;
    --repository)
      [ "$#" -ge 2 ] || { printf '%s\n' "--repository requires owner/name" >&2; exit 2; }
      repository=$2
      shift 2
      ;;
    *)
      printf '%s\n' "usage: $0 [--version 0.5.0] [--destination DIR] [--repository owner/name]" >&2
      exit 2
      ;;
  esac
done

case "$version" in
  *[!0-9A-Za-z._-]*|'') printf '%s\n' "unsafe version" >&2; exit 2 ;;
esac
case "$repository" in
  */*) ;;
  *) printf '%s\n' "repository must be owner/name" >&2; exit 2 ;;
esac
case "$repository" in
  *[!0-9A-Za-z._/-]*) printf '%s\n' "unsafe repository" >&2; exit 2 ;;
esac

os=$(uname -s 2>/dev/null || printf unknown)
arch=$(uname -m 2>/dev/null || printf unknown)
case "$arch" in
  x86_64|amd64) arch=x64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) printf '%s\n' "unsupported architecture: $arch; use scripts/install.sh for the portable Python build" >&2; exit 1 ;;
esac

case "$os" in
  Linux)
    libc=glibc
    if ldd --version 2>&1 | grep -qi musl || ls /lib/ld-musl-*.so.1 >/dev/null 2>&1; then
      libc=musl
    fi
    platform="linux-${libc}-${arch}"
    ;;
  Darwin) platform="macos-${arch}" ;;
  *) printf '%s\n' "unsupported operating system: $os; Windows users should run install-release.ps1" >&2; exit 1 ;;
esac

asset="JSON-API-Forge-v${version}-${platform}.tar.gz"
base="https://github.com/${repository}/releases/download/v${version}"
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/forge-install.XXXXXX")
cleanup() { rm -rf "$temporary_root"; }
trap cleanup EXIT HUP INT TERM

download() {
  source_url=$1
  output_path=$2
  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --proto '=https' --tlsv1.2 --retry 3 --output "$output_path" "$source_url"
  elif command -v wget >/dev/null 2>&1; then
    wget --https-only --tries=3 --output-document="$output_path" "$source_url"
  else
    printf '%s\n' "curl or wget is required" >&2
    exit 1
  fi
}

download "$base/$asset" "$temporary_root/$asset"
download "$base/$asset.sha256" "$temporary_root/$asset.sha256"
expected=$(awk 'NR==1 {print $1}' "$temporary_root/$asset.sha256")
case "$expected" in
  *[!0-9a-fA-F]*|'') printf '%s\n' "release checksum file is malformed" >&2; exit 1 ;;
esac
[ "${#expected}" -eq 64 ] || { printf '%s\n' "release checksum is not SHA-256" >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$temporary_root/$asset" | awk '{print $1}')
else
  actual=$(shasum -a 256 "$temporary_root/$asset" | awk '{print $1}')
fi
[ "$actual" = "$expected" ] || { printf '%s\n' "SHA-256 verification failed; nothing was installed" >&2; exit 1; }

if [ -z "$destination" ]; then
  destination="JSON-API-Forge-v${version}"
fi
if [ -e "$destination" ]; then
  printf '%s\n' "destination already exists: $destination" >&2
  exit 1
fi
mkdir -p "$destination"
tar -xzf "$temporary_root/$asset" -C "$destination"
printf '%s\n' "Installed verified JSON API Forge v${version} for ${platform} in $destination"
printf '%s\n' "Run '$destination/bin/forge --help' or '$destination/bin/forge-server --root YOUR_DEPLOYMENT_ROOT'."
