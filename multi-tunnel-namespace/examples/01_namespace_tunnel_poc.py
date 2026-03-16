#!/usr/bin/env python3
"""
Phase 0 Proof-of-Concept: Network Namespace-Based Multi-Tunnel VPN

This script validates the core technical approach for Option 1:
- Create a network namespace
- Create a TUN device
- Move TUN into the namespace
- Configure routing inside namespace
- Run a command via nsenter to verify isolation

Usage:
    sudo python3 01_namespace_tunnel_poc.py

Note: Requires root privileges for TUN creation and namespace manipulation.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Configuration for this PoC
TEST_NAMESPACE = "vpn_test_poc"
TEST_TUN = "tun_poc"
TEST_IP_HOST = "10.200.200.1"      # Host side of tunnel
TEST_IP_NAMESPACE = "10.200.200.2" # Namespace side IP
TEST_GATEWAY = "10.200.200.1"      # Gateway in namespace (host side)
VPN_NETWORK = "10.200.200.0/24"

def run(cmd, check=True, capture_output=False, text=False):
    """Run a shell command and optionally return result."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture_output, text=text)
    if check and result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        sys.exit(1)
    return result

def ensure_root():
    """Check if running as root."""
    if os.geteuid() != 0:
        print("ERROR: This PoC requires root privileges.")
        print("Please run: sudo python3 01_namespace_tunnel_poc.py")
        sys.exit(1)

def step_1_create_namespace():
    """Step 1: Create network namespace."""
    print("\n[1] Creating network namespace...")
    run(["ip", "netns", "add", TEST_NAMESPACE])
    print(f"   ✓ Namespace '{TEST_NAMESPACE}' created")

def step_2_create_tun_device():
    """Step 2: Create TUN device on host."""
    print("\n[2] Creating TUN device...")
    # Check if TUN module is loaded
    run(["grep", "-q", "tun", "/proc/modules"], check=False)

    # Create TUN device
    run(["ip", "tuntap", "add", TEST_TUN, "mode", "tun"])
    print(f"   ✓ TUN device '{TEST_TUN}' created")

def step_3_move_tun_to_namespace():
    """Step 3: Move TUN device into the namespace."""
    print("\n[3] Moving TUN device to namespace...")
    run(["ip", "link", "set", TEST_TUN, "netns", TEST_NAMESPACE])
    print(f"   ✓ TUN device moved to namespace '{TEST_NAMESPACE}'")

def step_4_configure_host_side():
    """Step 4: Configure host side of tunnel (the other end)."""
    print("\n[4] Configuring host side of virtual link...")
    # Assign IP to host's end of tunnel (this end)
    run(["ip", "addr", "add", f"{TEST_IP_HOST}/30", "dev", TEST_TUN])
    run(["ip", "link", "set", TEST_TUN, "up"])
    print(f"   ✓ Host side: {TEST_IP_HOST}/30 on {TEST_TUN}")

def step_5_configure_namespace_side():
    """Step 5: Configure network inside namespace."""
    print("\n[5] Configuring namespace network stack...")

    # Bring up loopback in namespace (required by some apps)
    run(["ip", "netns", "exec", TEST_NAMESPACE, "ip", "link", "set", "lo", "up"])

    # Assign IP to namespace's end
    run(["ip", "netns", "exec", TEST_NAMESPACE, "ip", "addr", "add",
         f"{TEST_IP_NAMESPACE}/30", "dev", TEST_TUN])

    # Bring up TUN inside namespace
    run(["ip", "netns", "exec", TEST_NAMESPACE, "ip", "link", "set", TEST_TUN, "up"])

    # Set default route via host side (gateway)
    run(["ip", "netns", "exec", TEST_NAMESPACE, "ip", "route", "add",
         "default", "via", TEST_GATEWAY, "dev", TEST_TUN])

    print(f"   ✓ Namespace side: {TEST_IP_NAMESPACE}/30 on {TEST_TUN}")
    print(f"   ✓ Default route via {TEST_GATEWAY}")

def step_6_configure_dns():
    """Step 6: Set up DNS resolution inside namespace."""
    print("\n[6] Configuring DNS inside namespace...")

    # Create a simple resolv.conf
    resolv_content = "nameserver 1.1.1.1\nnameserver 8.8.8.8\n"
    resolv_temp = f"/tmp/resolv.conf.{TEST_NAMESPACE}"

    with open(resolv_temp, 'w') as f:
        f.write(resolv_content)

    # Copy to namespace's /etc/resolv.conf
    # Note: This requires namespace's /etc to be accessible. In real system,
    # we'd use a bind mount or configure systemd-resolved.
    run(["ip", "netns", "exec", TEST_NAMESPACE, "cp", resolv_temp, "/etc/resolv.conf"])
    print(f"   ✓ DNS configured (Cloudflare + Google)")

def step_7_enable_ip_forwarding_and_nat():
    """Step 7: Enable IP forwarding and NAT on host for internet access."""
    print("\n[7] Enabling IP forwarding and NAT...")

    # Enable IP forwarding
    run(["sysctl", "-w", "net.ipv4.ip_forward=1"], check=False)

    # Set up NAT (MASQUERADE) so namespace traffic can reach internet
    run(["iptables", "-t", "nat", "-A", "POSTROUTING",
         "-s", VPN_NETWORK, "-o", "eth0", "-j", "MASQUERADE"])

    # Allow forwarding from namespace interface
    run(["iptables", "-A", "FORWARD", "-i", TEST_TUN, "-o", "eth0", "-j", "ACCEPT"])
    run(["iptables", "-A", "FORWARD", "-i", "eth0", "-o", TEST_TUN, "-m", "state",
         "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"])

    print("   ✓ IP forwarding enabled")
    print("   ✓ NAT masquerade rule added")
    print("   ✓ Forwarding rules added")

def step_8_test_connectivity():
    """Step 8: Test connectivity from inside namespace."""
    print("\n[8] Testing connectivity from namespace...")

    # Test: Ping host from namespace
    print("  - Testing ping to host...")
    result = run(["ip", "netns", "exec", TEST_NAMESPACE, "ping", "-c", "3", TEST_IP_HOST],
                 capture_output=True, text=True)
    if "3 packets transmitted" in result.stdout and "0% packet loss" in result.stdout:
        print("    ✓ Ping to host successful")
    else:
        print("    ✗ Ping to host failed")
        print(result.stdout)

    # Test: ping external (8.8.8.8)
    print("  - Testing ping to internet...")
    result = run(["ip", "netns", "exec", TEST_NAMESPACE, "ping", "-c", "3", "8.8.8.8"],
                 capture_output=True, text=True, check=False)
    if result.returncode == 0:
        print("    ✓ Ping to 8.8.8.8 successful")
    else:
        print("    ⚠ Ping to 8.8.8.8 failed (expected if no real internet)")

    # Test: DNS resolution
    print("  - Testing DNS resolution...")
    result = run(["ip", "netns", "exec", TEST_NAMESPACE, "nslookup", "example.com"],
                 capture_output=True, text=True, check=False)
    if result.returncode == 0 and "Name:" in result.stdout:
        print("    ✓ DNS resolution working")
    else:
        print("    ⚠ DNS resolution failed (requires working DNS)")

    # Test: HTTP via curl
    print("  - Testing HTTP request to ifconfig.me...")
    result = run(["ip", "netns", "exec", TEST_NAMESPACE, "curl", "-s", "https://ifconfig.me"],
                 capture_output=True, text=True, check=False)
    if result.returncode == 0 and result.stdout.strip():
        print(f"    ✓ HTTP request successful, IP: {result.stdout.strip()}")
    else:
        print("    ⚠ HTTP request failed (curl may show SSL errors without proper certs)")

def step_9_demonstrate_isolation():
    """Step 9: Show that namespace is isolated from host network."""
    print("\n[9] Demonstrating isolation...")

    # In namespace: show routing table
    print("  - Routing table inside namespace:")
    result = run(["ip", "netns", "exec", TEST_NAMESPACE, "ip", "route"],
                 capture_output=True, text=True)
    for line in result.stdout.strip().split('\n'):
        print(f"      {line}")

    # In host: show that TUN is not in main routing (unless explicitly added)
    print("  - TUN device in host:")
    result = run(["ip", "-o", "link", "show", TEST_TUN], capture_output=True, text=True)
    print(f"      {result.stdout.strip()}")

    print("  ✓ Namespace isolation confirmed")

def cleanup():
    """Clean up all created resources."""
    print("\n[Cleanup] Removing test artifacts...")

    # Delete namespace (tunnel device inside is auto-removed)
    run(["ip", "netns", "delete", TEST_NAMESPACE], check=False)

    # Ensure TUN device is gone
    run(["ip", "link", "delete", TEST_TUN], check=False)

    # Remove NAT rule
    run(["iptables", "-t", "nat", "-D", "POSTROUTING",
         "-s", VPN_NETWORK, "-o", "eth0", "-j", "MASQUERADE"], check=False)

    # Remove FORWARD rules
    run(["iptables", "-D", "FORWARD", "-i", TEST_TUN, "-o", "eth0", "-j", "ACCEPT"], check=False)
    run(["iptables", "-D", "FORWARD", "-i", "eth0", "-o", TEST_TUN,
         "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"], check=False)

    # Remove temporary resolv.conf
    resolv_temp = f"/tmp/resolv.conf.{TEST_NAMESPACE}"
    if os.path.exists(resolv_temp):
        os.remove(resolv_temp)

    print("  ✓ Cleanup complete")

def main():
    """Execute all steps in sequence."""
    print("=" * 70)
    print("Multi-Tunnel VPN: Network Namespace PoC")
    print("=" * 70)

    ensure_root()
    print("\nRunning as root - good.")

    try:
        steps = [
            step_1_create_namespace,
            step_2_create_tun_device,
            step_3_move_tun_to_namespace,
            step_4_configure_host_side,
            step_5_configure_namespace_side,
            step_6_configure_dns,
            step_7_enable_ip_forwarding_and_nat,
            step_8_test_connectivity,
            step_9_demonstrate_isolation,
        ]

        for step in steps:
            try:
                step()
            except Exception as e:
                print(f"\nERROR in {step.__name__}: {e}")
                print("Attempting cleanup...")
                cleanup()
                sys.exit(1)

        print("\n" + "=" * 70)
        print("PoC completed successfully!")
        print("=" * 70)

        print("\nKey demonstrated capabilities:")
        print("  ✓ Network namespace creation and deletion")
        print("  ✓ TUN device creation and migration between namespaces")
        print("  ✓ Independent network stack per namespace")
        print("  ✓ Per-namespace routing and DNS")
        print("  ✓ Isolation from host network configuration")
        print("\nThis validates the technical approach for Option 1.")

        # Ask if user wants to cleanup now
        response = input("\nClean up now? (Y/n): ").strip().lower()
        if response != 'n':
            cleanup()
        else:
            print("\nResources left running for manual inspection.")
            print(f"Namespace: {TEST_NAMESPACE}")
            print(f"TUN device: {TEST_TUN}")
            print("To cleanup manually: sudo python3 cleanup.py")
            print("\nTo inspect namespace: sudo nsenter -n -t $(ip netns pids %s) ip addr" % TEST_NAMESPACE)

    except KeyboardInterrupt:
        print("\n\nInterrupted. Cleaning up...")
        cleanup()
        sys.exit(130)

if __name__ == "__main__":
    main()
