#!/usr/bin/env python3
"""
WinAudio Executable Builder
Compiles WinAudio GUI & Server Suite into a standalone single-file Windows Executable (WinAudio.exe).
"""
import os
import sys
import subprocess

def build():
    print("=" * 60)
    print("        [Building WinAudio Native Windows Executable]")
    print("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(base_dir, "web")
    gui_file = os.path.join(base_dir, "gui.py")

    icon_path = os.path.join(web_dir, "favicon.ico")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "WinAudio",
        "--icon", icon_path,
        "--add-data", f"{web_dir};web",
        "--collect-all", "customtkinter",
        "--collect-all", "aiortc",
        "--collect-all", "av",
        "--clean",
        gui_file
    ]

    print(f"Executing: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=base_dir)

    if result.returncode == 0:
        exe_path = os.path.join(base_dir, "dist", "WinAudio.exe")
        print("\n" + "=" * 60)
        print(" [SUCCESS] WinAudio.exe successfully created!")
        print(f" Location: {exe_path}")
        print("=" * 60)
    else:
        print(f"\n[ERROR] Build failed with return code {result.returncode}")

if __name__ == "__main__":
    build()
