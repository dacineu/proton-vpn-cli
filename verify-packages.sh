#!/bin/bash
# Verify Arch packages are valid

echo "=== Verifying Arch Packages ==="
echo ""

PKG_DIR="/home/dacineu/dev/proton-vpn-cli/packaging/arch/pkg"

echo "1. Checking proton-vpn-manager package..."
if [ -f "${PKG_DIR}/proton-vpn-manager-0.1.8-2-any.pkg.tar.zst" ]; then
    echo "   ✓ Package exists"
    # Check metadata
    if zstd -dc "${PKG_DIR}/proton-vpn-manager-0.1.8-2-any.pkg.tar.zst" 2>/dev/null | tar -t .PKGINFO >/dev/null 2>&1; then
        echo "   ✓ .PKGINFO present"
    else
        echo "   ✗ .PKGINFO missing"
    fi
    if zstd -dc "${PKG_DIR}/proton-vpn-manager-0.1.8-2-any.pkg.tar.zst" 2>/dev/null | tar -t .MTREE >/dev/null 2>&1; then
        echo "   ✓ .MTREE present"
    else
        echo "   ✗ .MTREE missing"
    fi
    if zstd -dc "${PKG_DIR}/proton-vpn-manager-0.1.8-2-any.pkg.tar.zst" 2>/dev/null | tar -t .INSTALL >/dev/null 2>&1; then
        echo "   ✓ .INSTALL present"
    else
        echo "   ✗ .INSTALL missing"
    fi
    # Check key files
    if zstd -dc "${PKG_DIR}/proton-vpn-manager-0.1.8-2-any.pkg.tar.zst" 2>/dev/null | tar -t | grep -q "/usr/bin/proton-vpn-manager"; then
        echo "   ✓ Daemon binary present"
    else
        echo "   ✗ Daemon binary missing"
    fi
    if zstd -dc "${PKG_DIR}/proton-vpn-manager-0.1.8-2-any.pkg.tar.zst" 2>/dev/null | tar -t | grep -q "/usr/lib/systemd/system/proton-vpn-manager.service"; then
        echo "   ✓ Systemd service present"
    else
        echo "   ✗ Systemd service missing"
    fi
else
    echo "   ✗ Package not found"
fi

echo ""
echo "2. Checking proton-vpn-cli package..."
if [ -f "${PKG_DIR}/proton-vpn-cli-0.1.8-2-any.pkg.tar.zst" ]; then
    echo "   ✓ Package exists"
    if zstd -dc "${PKG_DIR}/proton-vpn-cli-0.1.8-2-any.pkg.tar.zst" 2>/dev/null | tar -t .PKGINFO >/dev/null 2>&1; then
        echo "   ✓ .PKGINFO present"
    else
        echo "   ✗ .PKGINFO missing"
    fi
    if zstd -dc "${PKG_DIR}/proton-vpn-cli-0.1.8-2-any.pkg.tar.zst" 2>/dev/null | tar -t | grep -q "/usr/bin/protonvpn"; then
        echo "   ✓ CLI binary present"
    else
        echo "   ✗ CLI binary missing"
    fi
else
    echo "   ✗ Package not found"
fi

echo ""
echo "=== Verification Complete ==="
echo ""
echo "To install on Arch:"
echo "  sudo pacman -U ${PKG_DIR}/proton-vpn-manager-0.1.8-2-any.pkg.tar.zst"
echo "  sudo pacman -U ${PKG_DIR}/proton-vpn-cli-0.1.8-2-any.pkg.tar.zst"
