#!/usr/bin/env bash
# update_checksums.sh - Update SHA256 checksums for the PKGBUILD source tarball

set -euo pipefail

PKGBUILD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PKGBUILD_DIR"

if [[ ! -f "PKGBUILD" ]]; then
    echo "Error: PKGBUILD not found in $(pwd)"
    exit 1
fi

# Parse pkgver from PKGBUILD
pkgver=$(grep '^pkgver=' PKGBUILD | cut -d= -f2)
if [[ -z "$pkgver" ]]; then
    echo "Error: Could not extract pkgver from PKGBUILD"
    exit 1
fi

# Download the source tarball (if not already present)
tarball="v${pkgver}.tar.gz"
url="https://github.com/ProtonMail/python-protonvpn-cli/archive/refs/tags/${tarball}"

echo "Downloading ${url}..."
curl -sL -o "${tarball}" "${url}"

# Compute SHA256
sha256=$(sha256sum "${tarball}" | awk '{print $1}')
echo "SHA256: ${sha256}"

# Update PKGBUILD
if grep -q "sha256sums=('SKIP')" PKGBUILD; then
    sed -i "s/sha256sums=('SKIP')/sha256sums=('${sha256}')/" PKGBUILD
    echo "Updated PKGBUILD with checksum."
else
    # Replace existing checksum
    sed -i "s/sha256sums=('.*')/sha256sums=('${sha256}')/" PKGBUILD
    echo "Updated existing checksum in PKGBUILD."
fi

# Clean up tarball
rm -f "${tarball}"

echo "Done. You can now run: makepkg -si"
