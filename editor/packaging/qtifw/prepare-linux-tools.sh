#!/usr/bin/env bash
set -euo pipefail

# Print only the tool directory to stdout (the workflow appends it to GITHUB_PATH).
binarycreator=${1:?usage: prepare-linux-tools.sh /path/to/binarycreator}
binarycreator=$(realpath "$binarycreator")
bin_dir=$(dirname "$binarycreator")
if [[ $(uname -m) == aarch64 ]]; then
  # IFW 4.8.1 ARM64 tools require the TIFF 5 ABI. Noble ships TIFF 6.
  # Keep the verified Jammy compatibility library private to the build tool.
  # Never symlink incompatible ABIs or add this directory to the Editor runtime.
  compat_root="$bin_dir/../compat-tiff5"
  mkdir -p "$compat_root"
  package="$compat_root/libtiff5.deb"
  curl --proto '=https' --proto-redir '=https' --tlsv1.2 --fail --location --retry 3 \
    --output "$package" \
    'https://ports.ubuntu.com/ubuntu-ports/pool/main/t/tiff/libtiff5_4.3.0-6ubuntu0.13_arm64.deb'
  echo "41db53b54493c6be85f357adfae747ff5d30c443a633e2199dc6ffa4143a88b4  $package" | sha256sum -c - >&2
  dpkg-deb -x "$package" "$compat_root"
  test -f "$compat_root/usr/lib/aarch64-linux-gnu/libtiff.so.5"
  wrapper_dir="$bin_dir/../wrapped-bin"
  mkdir -p "$wrapper_dir"
  cat > "$wrapper_dir/binarycreator" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
ifw_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export LD_LIBRARY_PATH="$ifw_root/compat-tiff5/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$ifw_root/bin/binarycreator" "$@"
WRAPPER
  chmod 0755 "$wrapper_dir/binarycreator"
  binarycreator="$wrapper_dir/binarycreator"
  bin_dir="$wrapper_dir"
fi
# Detect loader failures immediately, before compiling and archiving the Editor.
"$binarycreator" --help >&2
printf '%s\n' "$bin_dir"
