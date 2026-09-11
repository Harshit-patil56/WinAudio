#!/usr/bin/env python3
"""
WinAudio Executable Builder
Compiles WinAudio GUI & Server Suite into a standalone Windows Executable (WinAudio.exe)
with pre-packaged Android Platform Tools (ADB) for seamless zero-setup USB streaming.
Also creates a GitHub-ready release archive (WinAudio-v1.0.0-Windows-x64.zip).
"""
import os
import sys
import shutil
import subprocess

def clean_old_builds(base_dir):
    print("[1/4] Cleaning previous build artifacts...")
    for folder in ["build", "dist"]:
        folder_path = os.path.join(base_dir, folder)
        if os.path.exists(folder_path):
            print(f"  Removing {folder_path}...")
            shutil.rmtree(folder_path, ignore_errors=True)
    print("  Previous builds purged successfully.\n")

def build():
    print("=" * 70)
    print("        [Building WinAudio Native Executable with Bundled ADB]")
    print("=" * 70)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(base_dir, "web")
    platform_tools_dir = os.path.join(base_dir, "platform-tools")
    gui_file = os.path.join(base_dir, "gui.py")
    icon_path = os.path.join(web_dir, "favicon.ico")

    # 1. Clean previous build folders
    clean_old_builds(base_dir)

    # 2. Verify bundled ADB exists
    if not os.path.exists(os.path.join(platform_tools_dir, "adb.exe")):
        print(f"[ERROR] platform-tools/adb.exe not found at {platform_tools_dir}!")
        sys.exit(1)
    print(f"[2/4] Verified bundled ADB at: {platform_tools_dir}\n")

    # 3. Run PyInstaller to compile single-file WinAudio.exe
    print("[3/4] Compiling WinAudio.exe with PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "WinAudio",
        "--icon", icon_path,
        "--add-data", f"{web_dir};web",
        "--add-data", f"{platform_tools_dir};platform-tools",
        "--collect-all", "customtkinter",
        "--collect-all", "aiortc",
        "--collect-all", "av",
        "--clean",
        gui_file
    ]

    print(f"Executing: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=base_dir)

    if result.returncode != 0:
        print(f"\n[ERROR] Build failed with return code {result.returncode}")
        sys.exit(result.returncode)

    exe_path = os.path.join(base_dir, "dist", "WinAudio.exe")
    if not os.path.exists(exe_path):
        print("\n[ERROR] WinAudio.exe not found in dist/!")
        sys.exit(1)

    print("\n[SUCCESS] Standalone WinAudio.exe successfully compiled!")
    print(f"  Path: {exe_path} ({os.path.getsize(exe_path) / (1024 * 1024):.1f} MB)\n")

    # 4. Create GitHub Release Package (Folder & Zip)
    print("[4/4] Creating GitHub Release Distribution Package...")
    release_name = "WinAudio-v1.0.0-Windows-x64"
    release_dir = os.path.join(base_dir, "dist", release_name)
    os.makedirs(release_dir, exist_ok=True)

    # Copy WinAudio.exe
    shutil.copy2(exe_path, os.path.join(release_dir, "WinAudio.exe"))

    # Copy platform-tools folder
    dest_platform_tools = os.path.join(release_dir, "platform-tools")
    if os.path.exists(dest_platform_tools):
        shutil.rmtree(dest_platform_tools)
    shutil.copytree(platform_tools_dir, dest_platform_tools)

    # Create README.txt with quick-start instructions
    readme_content = """========================================================================
 WinAudio - Low-Latency PC-to-Phone Audio Streaming (Windows 11)
 Version: 1.0.0 (x64)
========================================================================

QUICK START INSTRUCTIONS:

1. WI-FI STREAMING (Wireless):
   - Make sure your PC and Phone are connected to the same Wi-Fi network.
   - Run WinAudio.exe.
   - Scan the Wi-Fi QR code with your phone camera, or open the Network IP in your phone browser.
   - Tap "Start Audio Stream".

2. USB STREAMING (Zero-Lag, Bit-Perfect 48kHz Stereo):
   - Connect your phone to your PC with a USB cable.
   - On your phone: Go to Settings -> Developer Options -> Turn ON "USB Debugging".
   - Run WinAudio.exe.
     (Android Platform Tools / ADB is already pre-packaged! No SDK or PATH setup needed.)
   - On WinAudio Control Center, switch the QR toggle to "USB (Localhost)".
   - Scan the QR code or open http://localhost:8080 on Chrome on your phone.
   - Tap "Start Audio Stream" and enjoy ultra-low latency audio!

========================================================================
"""
    with open(os.path.join(release_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)

    # Create ZIP archive for GitHub Releases
    zip_path = os.path.join(base_dir, "dist", release_name)
    shutil.make_archive(zip_path, "zip", root_dir=os.path.join(base_dir, "dist"), base_dir=release_name)

    print("=" * 70)
    print(" [ALL COMPLETE] GitHub Release Artifacts Ready in dist/:")
    print(f"  1. Standalone Executable: {exe_path}")
    print(f"  2. Release Folder:       {release_dir}")
    print(f"  3. GitHub Release Zip:   {zip_path}.zip ({os.path.getsize(zip_path + '.zip') / (1024 * 1024):.1f} MB)")
    print("=" * 70)

if __name__ == "__main__":
    build()
