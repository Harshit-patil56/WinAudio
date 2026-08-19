# 🔊 WinAudio

<div align="center">

![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010-0078D4?style=for-the-badge&logo=windows11&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Audio Engine](https://img.shields.io/badge/Audio-WASAPI%20Loopback%20%2B%20MMCSS-60CDFF?style=for-the-badge&logo=soundcharts&logoColor=black)
![Protocols](https://img.shields.io/badge/Streaming-WebRTC%20%7C%20WebSocket-BF5AF2?style=for-the-badge)
![Latency](https://img.shields.io/badge/Latency-~8ms%20(USB)%20%7C%20~18ms%20(Wi--Fi)-30D158?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-F5A623?style=for-the-badge)

**Turn any smartphone (Android / iOS) into an ultra-low latency wireless or USB external speaker for your Windows PC.**

[Features](#-key-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Connection Modes](#-connection-modes) • [Building EXE](#-build-standalone-executable) • [Troubleshooting](#-troubleshooting--faq)

</div>

---

## 📖 Overview

**WinAudio** is a high-performance audio streaming system engineered to broadcast bit-perfect PC system audio to mobile devices in real time. 

By combining Windows **WASAPI Loopback Capture (`IAudioClient3`)** elevated to **MMCSS "Pro Audio" priority** with a client-side **WebAudio `AudioWorklet` circular ring buffer**, WinAudio achieves studio-grade audio delivery with latencies as low as **~8–12ms over USB** and **~18–25ms over Wi-Fi**.

No mobile apps or app store installations required—any modern mobile web browser (Chrome, Safari, Firefox, Edge) acts as a full-fidelity audio receiver.

---

## ✨ Key Features

### 🎧 Low-Latency Audio Engine
- **WASAPI Loopback Capture**: Directly intercepts Windows master audio output using native COM interfaces with sub-millisecond buffer cycles.
- **MMCSS Thread Elevation**: Automatically registers capture threads with Windows Multimedia Class Scheduler Service (`AvSetMmThreadCharacteristicsW("Pro Audio")`) to prevent audio dropouts under high CPU load.
- **Dual Streaming Protocols**:
  - **WebRTC (UDP + Opus 48kHz)**: Ultra-low latency real-time transport with dynamic jitter adaptation and DTLS/SRTP encryption.
  - **WebSocket Binary Stream (TCP)**: High-fidelity uncompressed 48kHz 16-bit stereo PCM audio with `TCP_NODELAY`.

### 💻 Native Windows 11 Fluent Control Center
- **Microsoft Fluent Design System**: Built with authentic dark Mica canvas (`#202020`), acrylic surface cards (`#2B2B2B`), 8px/4px standard radii, and Segoe UI Variable typography hierarchy.
- **Harmonic Sine Wave Visualizer**: 3-layer real-time acoustic waveform canvas (Accent Blue, Violet, Mint) driven by fluid spring physics and dynamic AGC peak normalization.
- **Live Hardware ADB Detection**: Real-time background polling for connected USB devices with visual status capsules.
- **Dynamic QR Code & URL Badges**: Instant pairing with one-click clipboard copy for both Wi-Fi LAN and USB localhost endpoints.
- **System Tray Integration**: Runs quietly in the background with custom Fluent stereo receiver tray icon and minimize-to-tray capability.

### 📱 Zero-Install Mobile Receiver
- **WebAudio AudioWorklet Architecture**: Offloads audio processing from the browser's main thread to dedicated audio rendering threads.
- **Dynamic Drift & Jitter Correction**: Circular ring buffer automatically compensates for clock drift between PC and phone hardware without audio pitch artifacts.
- **Glassmorphic Mobile UI**: Real-time spectrum visualizer, live latency readouts, adjustable buffer tuning slider, volume control, and wake-lock to prevent phone sleep during playback.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                              WINDOWS PC                                │
│                                                                        │
│   Windows Audio Engine ──► WASAPI Loopback Capture (IAudioClient3)     │
│                                       │                                │
│                         MMCSS Pro Audio Thread Priority                │
│                                       │                                │
│                  ┌────────────────────┴───────────────────┐            │
│                  ▼                                        ▼            │
│         WebRTC Server (UDP)                     WebSocket Server (TCP) │
│       Opus 48kHz / Low-Latency                  Raw PCM 48kHz Stereo   │
│                  │                                        │            │
│                  ├────────────────────┬───────────────────┤            │
│                  ▼                    ▼                   ▼            │
│          USB Cable (ADB)       Wi-Fi (5G / 2.4G)    USB Tethering      │
└──────────────────┬────────────────────┬───────────────────┬────────────┘
                   │                    │                   │
                   ▼                    ▼                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        SMARTPHONE (Android / iOS)                      │
│                                                                        │
│                      Browser AudioWorklet Node                         │
│                                  │                                     │
│                     Circular Jitter Ring Buffer                        │
│                                  │                                     │
│                     Dynamic Drift Compensation                         │
│                                  │                                     │
│                            Phone Speaker                               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Connection Modes

| Mode | Latency | Wi-Fi Needed? | Jitter / Stability | Best Used For |
| :--- | :--- | :--- | :--- | :--- |
| **🔌 USB (ADB Reverse)** | **~8–12 ms** | ❌ No | Near Zero | Gaming, movies, real-time video editing |
| **📶 Wi-Fi LAN (5 GHz)** | **~18–25 ms** | ✅ Yes | Very Low | Casual listening, workspace speaker |
| **📶 Wi-Fi LAN (2.4 GHz)**| **~25–40 ms** | ✅ Yes | Low–Medium | Extended range across rooms |
| **🔗 USB Tethering (RNDIS)**| **~10–15 ms** | ❌ No | Very Low | Plug-and-play wired network mode |

---

## 🚀 Quick Start

### Prerequisites
- **Windows 10 / 11** (64-bit)
- **Python 3.10+** (if running from source)
- Any smartphone connected via Wi-Fi or USB

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Harshit-patil56/WinAudio.git
   cd WinAudio
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

#### Option A: Native Windows 11 GUI (Recommended)
Launch the desktop control center:
```bash
python gui.py
```

#### Option B: Headless / CLI Server
Launch the server directly from the command line:
```bash
python app.py
```

---

## 📱 Connecting Your Phone

### 1. Connecting via Wi-Fi (Wireless)
1. Ensure your PC and phone are on the same Wi-Fi network.
2. Launch `python gui.py` (or `python app.py`).
3. Scan the **QR Code** on the screen using your phone's camera, or manually navigate to the URL shown (e.g., `http://192.168.1.100:8080`).
4. Tap **"Start PC Speaker Stream"** on your phone.

---

### 2. Connecting via USB Cable (Zero-Latency, No Wi-Fi)
For the absolute lowest latency and zero wireless interference, connect via USB:

1. **Enable USB Debugging** on your Android phone:
   - Go to *Settings → About Phone* and tap *Build Number* 7 times.
   - Go to *Settings → Developer Options* and turn on **USB Debugging**.
2. **Connect phone to PC** via USB cable and allow the USB Debugging RSA prompt on your phone.
3. Launch `python gui.py`. The USB indicator will turn **green** (`USB (ADB): Connected`).
4. On your phone's browser (Chrome/Firefox/Edge), open:
   ```
   http://localhost:8080
   ```
   *(Traffic routes directly through the USB cable via ADB reverse port forwarding)*
5. Turn off Wi-Fi on your phone if you wish to verify completely isolated wired streaming!

---

## 🔨 Build Standalone Executable

You can compile WinAudio into a single standalone `.exe` that includes all dependencies, UI assets, and the application icon:

```bash
python build_exe.py
```

Once compilation completes, the portable executable is located at:
```
dist/WinAudio.exe
```

---

## 🧪 Latency & Throughput Benchmark

WinAudio includes an automated testing client to benchmark loopback capture and streaming throughput:

```bash
python test_client.py
```

This runs synthetic streaming tests, measures packet jitter, checks sample fidelity, and reports roundtrip latency metrics.

---

## 📁 Project Structure

```
WinAudio/
├── gui.py                         # Windows 11 Fluent Desktop Control Center
├── app.py                         # CLI Server Launcher & Interactive Console
├── build_exe.py                   # PyInstaller Standalone Executable Builder
├── test_client.py                 # Automated Network & Latency Benchmark Tool
├── requirements.txt               # Project Dependencies
│
├── server/
│   ├── audio_capture.py           # WASAPI Loopback Engine (MMCSS Pro Audio)
│   ├── network_server.py          # WebRTC & WebSocket Streaming Server
│   ├── webrtc_track.py            # Custom aiortc AudioStreamTrack (Opus 48kHz)
│   ├── adb_helper.py              # ADB Reverse USB Tunneling & IP Detection
│   └── zeroconf_service.py        # mDNS Network Service Discovery
│
└── web/
    ├── index.html                 # Mobile Web App (PWA & Glassmorphism UI)
    ├── styles.css                 # Responsive Fluent / Glassmorphism Stylesheet
    ├── app.js                     # WebRTC / WebSocket Client Controller
    ├── audio-worklet-processor.js # High-Performance AudioWorklet Ring Buffer
    ├── icon.png                   # Web Application Icon
    └── favicon.ico                # Multi-resolution Application Icon
```

---

## ❓ Troubleshooting & FAQ

<details>
<summary><b>1. No sound is playing on my phone after clicking Start</b></summary>

- Modern mobile browsers require user interaction to play audio. Make sure you tapped **"Start PC Speaker Stream"**.
- Ensure your phone is not in Silent/Do Not Disturb mode and media volume is turned up.
- Verify audio is actively playing on your PC (the waveform in the desktop app will bounce).
</details>

<details>
<summary><b>2. How do I achieve the lowest possible latency?</b></summary>

- Use **USB Connection** with ADB reverse forwarding (`http://localhost:8080`).
- If using Wi-Fi, connect to a **5 GHz** Wi-Fi band instead of 2.4 GHz.
- In the mobile web UI, adjust the **Target Buffer Slider** down to `10ms` or `15ms`.
</details>

<details>
<summary><b>3. USB Mode says "ADB not found" or "No USB device"</b></summary>

- Download [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) and add `adb` to your Windows `PATH`.
- Verify your phone is recognized by running `adb devices` in PowerShell or Command Prompt.
- Accept the "Allow USB Debugging" dialog prompt on your phone's screen.
</details>

<details>
<summary><b>4. Windows Firewall blocked the connection</b></summary>

- Allow Python / `WinAudio.exe` through Windows Defender Firewall when prompted.
- WinAudio uses **TCP port 8080** for HTTP/WebSocket and dynamic UDP ports for WebRTC.
</details>

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.

---

<div align="center">
Built with ❤️ for ultra-low latency Windows audio streaming.
</div>
