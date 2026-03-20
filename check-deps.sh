#!/usr/bin/env bash
# Check system dependencies required for running the protonvpn binaries

echo "Checking system dependencies for Proton VPN CLI binaries..."
echo ""

missing=0

# Check for dbus (libdbus-1)
echo -n "libdbus-1... "
if ldconfig -p 2>/dev/null | grep -q libdbus-1; then
    echo "✓ found"
else
    echo "✗ missing (install: dbus)"
    missing=1
fi

# Check for systemd (libsystemd)
echo -n "libsystemd... "
if ldconfig -p 2>/dev/null | grep -q libsystemd; then
    echo "✓ found"
else
    echo "✗ missing (install: systemd)"
    missing=1
fi

# Check for wireguard (libwg)
echo -n "libwireguard... "
if ldconfig -p 2>/dev/null | grep -q libwireguard; then
    echo "✓ found"
else
    # Also check for wg command as fallback
    if command -v wg &>/dev/null; then
        echo "✓ wg tool found (library may be optional)"
    else
        echo "✗ missing (install: wireguard-tools)"
        missing=1
    fi
fi

# Check for Python (if user wants to install wheel)
echo -n "python3... "
if command -v python3 &>/dev/null; then
    echo "✓ found (for optional libvpnmanager wheel)"
else
    echo "⊘ not found (optional, only needed for libvpnmanager wheel)"
fi

# Check if running as root for some operations
echo ""
if [ $EUID -eq 0 ]; then
    echo "Note: Running as root. Some operations may require root, but binaries"
    echo "      themselves should be run as regular user (daemon runs as root via systemd)."
else
    echo "Running as normal user. You can install binaries to /usr/local/bin with sudo."
fi

echo ""
if [ $missing -eq 0 ]; then
    echo "All required system libraries are present."
    echo "You can now build or run the binaries."
    exit 0
else
    echo "Missing some system libraries. Install them before using the binaries."
    exit 1
fi
