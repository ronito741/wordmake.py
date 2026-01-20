
#!/usr/bin/env python3

import sys
import subprocess

REQUIRED = [
    "PyQt5"
]

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def main():
    print("🔧 Installing dependencies...")

    # Upgrade pip
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])

    # Install requirements
    for pkg in REQUIRED:
        print(f"➡ Installing {pkg}...")
        install(pkg)

    print("\n✅ Installation complete!")
    print("Run the tool with: python3 wordmake.py")

if __name__ == "__main__":
    main()
