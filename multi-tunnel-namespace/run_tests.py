#!/usr/bin/env python3
"""
Test runner script for the multi-tunnel VPN project.

Usage:
    python run_tests.py [options]

Examples:
    python run_tests.py                    # Run all unit tests
    python run_tests.py --unit             # Run unit tests only
    python run_tests.py --integration      # Run integration tests (requires daemon)
    python run_tests.py --system           # Run system tests (requires full setup)
    python run_tests.py --coverage         # Run with coverage report
    python run_tests.py --watch            # Watch mode (rerun on changes)
    python run_tests.py -m "not slow"      # Skip slow tests
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_cmd(cmd, cwd=None):
    """Run a command and return exit code."""
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def check_editable_install():
    """Check if libvpnmanager is installed in editable mode."""
    try:
        import libvpnmanager
        print(f"✓ libvpnmanager found: {libvpnmanager.__file__}")
        return True
    except ImportError:
        print("✗ libvpnmanager not installed")
        print("\nTo install:")
        print("  cd src/libvpnmanager && pip install -e \".[test]\"")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run test suite")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--system", action="store_true", help="Run system tests")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage")
    parser.add_argument("--watch", "-w", action="store_true", help="Watch mode (requires pytest-watch)")
    parser.add_argument("-m", help=" pytest marker expression (e.g., 'not slow')")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--install-deps", action="store_true", help="Install test dependencies first")
    parser.add_argument("file", nargs="?", help="Specific test file or directory")

    args = parser.parse_args()

    # If no test type specified, default to unit tests
    if not (args.unit or args.integration or args.system):
        args.unit = True

    # Check if libvpnmanager is installed
    if not check_editable_install():
        print("\nWould you like to install it now? (y/n)")
        if input().lower() == 'y':
            code = run_cmd(["pip", "install", "-e", ".[test]"], cwd="src/libvpnmanager")
            if code != 0:
                print("Installation failed")
                return code
        else:
            return 1

    # Install dependencies if requested
    if args.install_deps:
        print("\nInstalling test dependencies...")
        deps = ["pytest", "pytest-asyncio", "pytest-mock", "pytest-cov"]
        code = run_cmd([sys.executable, "-m", "pip", "install", "--upgrade"] + deps)
        if code != 0:
            return code

    # Build pytest command
    pytest_cmd = ["pytest"]

    if args.verbose:
        pytest_cmd.append("-v")

    if args.coverage:
        pytest_cmd.extend(["--cov=libvpnmanager", "--cov-report=term", "--cov-report=html"])

    if args.watch:
        try:
            import pytest_watch
        except ImportError:
            print("pytest-watch not installed. Install with: pip install pytest-watch")
            return 1
        pytest_cmd = ["ptw"] + pytest_cmd[1:]

    if args.m:
        pytest_cmd.extend(["-m", args.m])

    # Determine test path
    test_paths = []
    if args.unit:
        test_paths.append("tests/unit")
    if args.integration:
        test_paths.append("tests/integration")
    if args.system:
        test_paths.append("tests/system")

    if args.file:
        test_paths = [args.file]

    pytest_cmd.extend(test_paths)

    # Run tests
    print(f"\nRunning: {' '.join(pytest_cmd)}\n")
    return run_cmd(pytest_cmd, cwd="tests")


if __name__ == "__main__":
    sys.exit(main())
