#!/usr/bin/env python
"""Simple test script to verify PyInstaller works."""
import sys
import platform

def main():
    print("Hello from PyInstaller!")
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print("This demonstrates that Python is embedded in the binary.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
