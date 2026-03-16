#!/bin/bash
# Build a proper Arch package for proton-vpn-manager using fakeroot
set -e

REPO_ROOT="/home/dacineu/dev/proton-vpn-cli"
BUILD_DIR="/tmp/proton-vpn-manager-build"
PKG_DIR="${BUILD_DIR}/pkg"
DST_DIR="${REPO_ROOT}/multi-tunnel-namespace/packaging/arch/pkg"
PKGNAME="proton-vpn-manager"
PKGVER="0.1.8-1"

echo "=== Building Arch package for proton-vpn-manager ==="
echo "Repo root: ${REPO_ROOT}"
echo "Build dir: ${BUILD_DIR}"
echo "Package: ${PKGNAME}-${PKGVER}-any.pkg.tar.zst"

# Clean build directories
rm -rf "${BUILD_DIR}" "${DST_DIR}"
mkdir -p "${BUILD_DIR}/src" "${PKG_DIR}" "${DST_DIR}"

# Copy source code
echo "Copying source..."
cp -r "${REPO_ROOT}/multi-tunnel-namespace/src" "${BUILD_DIR}/"
cp -r "${REPO_ROOT}/multi-tunnel-namespace/packaging" "${BUILD_DIR}/"
# Copy documentation
for doc in README.md MULTI_TUNNEL_ARCHITECTURE.md IMPLEMENTATION_REPORT.md TODO_OPTION1.md; do
    [ -f "${REPO_ROOT}/${doc}" ] && cp "${REPO_ROOT}/${doc}" "${BUILD_DIR}/" || true
done

# Build libvpnmanager wheel
echo "Building libvpnmanager wheel..."
cd "${BUILD_DIR}/src"
pip wheel . --wheel-dir "${BUILD_DIR}" --no-deps

# Find the built wheel
WHEEL=$(ls "${BUILD_DIR}"/*.whl | head -n1)
echo "Wheel: $(basename "${WHEEL}")"

# Install wheel into package directory (using fakeroot)
echo "Installing into package staging..."
fakeroot /bin/bash -c "
set -e
mkdir -p '${PKG_DIR}'
cd '${BUILD_DIR}'
python -m installer --destdir='${PKG_DIR}' '$(basename "${WHEEL}")'
"

# Install daemon, service, polkit, docs
echo "Installing additional files..."
fakeroot /bin/bash -c "
set -e
install -Dm755 '${BUILD_DIR}/src/daemon/daemon.py' '${PKG_DIR}/usr/bin/proton-vpn-manager'
install -Dm644 '${BUILD_DIR}/packaging/systemd/usr/lib/systemd/system/proton-vpn-manager.service' '${PKG_DIR}/usr/lib/systemd/system/proton-vpn-manager.service'
install -Dm644 '${BUILD_DIR}/packaging/polkit/60-protonvpn-manager.rules' '${PKG_DIR}/etc/polkit-1/rules.d/60-protonvpn-manager.rules'
install -Dm644 '${BUILD_DIR}/README.md' '${PKG_DIR}/usr/share/doc/${PKGNAME}/README.md' 2>/dev/null || true
install -Dm644 '${BUILD_DIR}/MULTI_TUNNEL_ARCHITECTURE.md' '${PKG_DIR}/usr/share/doc/${PKGNAME}/ARCHITECTURE.md' 2>/dev/null || true
install -Dm644 '${BUILD_DIR}/src/libvpnmanager/README.md' '${PKG_DIR}/usr/share/doc/${PKGNAME}/LIBVPNMANAGER.md' 2>/dev/null || true
install -Dm644 '${BUILD_DIR}/IMPLEMENTATION_REPORT.md' '${PKG_DIR}/usr/share/doc/${PKGNAME}/IMPLEMENTATION_REPORT.md' 2>/dev/null || true
"

# Generate .PKGINFO
echo "Generating .PKGINFO..."
PKGINFO="${PKG_DIR}/.PKGINFO"
cat > "${PKGINFO}" <<EOF
# Arch Linux package metadata
pkgname = ${PKGNAME}
pkgver = ${PKGVER}
pkgdesc = Proton VPN Tunnel Manager daemon for multi-tunnel VPN with network namespace isolation
url = https://github.com/ProtonMail/python-protonvpn-cli
builddate = $(date +%s)
packager = dacineu <dacineu@pm.me>
size = $(du -sk "${PKG_DIR}" | cut -f1)
arch = any
license = GPL3
depends = python python-dbus-fast python-pydantic python-asyncstdlib python-pyroute2 iproute2 nsenter
optdepends = proton-vpn-cli: Multi-tunnel VPN support (tunnel commands)
backup = etc/polkit-1/rules.d/60-protonvpn-manager.rules
EOF

# Generate .MTREE (simplified: list all files with mode, owner, group)
echo "Generating .MTREE..."
MTREE="${PKG_DIR}/.MTREE"
(
cd "${PKG_DIR}"
find . -type f | while read -r file; do
    # Default values: root:root, mode based on file type
    # Use stat to get mode, uid, gid, size, mtime
    STAT=$(stat -c "%a %u %g %s %Y" "$file")
    read -r mode uid gid size mtime <<< "$STAT"
    # Remove leading ./ for mtree path
    path="${file#./}"
    printf "%s %s %s %s %s\n" "$path" "$mode" "$uid" "$gid" "$size" "$mtime"
done
) > "${MTREE}" 2>/dev/null || true
# Note: .MTREE format is more complex; this is minimal

# Include the install script from the packaging directory
echo "Adding install script..."
cp "${REPO_ROOT}/multi-tunnel-namespace/packaging/arch/proton-vpn-manager.install" "${PKG_DIR}/.INSTALL" 2>/dev/null || true

# Create the final package tarball
echo "Creating package tarball..."
cd "${PKG_DIR}"
TARBALL="${DST_DIR}/${PKGNAME}-${PKGVER}-any.pkg.tar.zst"
tar -c --format=posix --xattrs --acls --sort=name . | zstd -T0 -z -o "${TARBALL}" --format=zstd

# Verify package size
echo ""
echo "=== Build complete ==="
echo "Package: ${TARBALL}"
echo "Size: $(du -h "${TARBALL}" | cut -f1)"
