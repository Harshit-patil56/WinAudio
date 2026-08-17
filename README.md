# 🔊 WinAudio

**WinAudio** is a high-performance, ultra-low latency Windows application that transforms any smartphone (Android or iOS) into a wireless or USB external speaker for your PC.

Using Windows **WASAPI Loopback Capture (`IAudioClient3`)** with MMCSS priority and a **WebAudio AudioWorklet ring buffer**, WinAudio achieves near-native audio streaming with delay down to **~8-12ms over USB** and **~18-25ms over Wi-Fi**.

---

## ✨ Features

- ⚡ **Ultra-Low Latency**: ~10ms buffer size via WASAPI loopback and AudioWorklet circular ring buffer.
- 🔌 **Multiple Connection Methods**:
  - **USB Connection (Primary)**: Zero-latency streaming via ADB port forwarding (`adb forward tcp:8080 tcp:8080`) or USB Tethering.
  - **Wi-Fi Connection**: Seamless wireless streaming on 5GHz / 2.4GHz local networks.
  - **mDNS Auto-Discovery**: Automatic network service broadcasting via Zeroconf.
- 📱 **Zero-Install Mobile Client**: Instant connection on Android & iOS via web client & PWA—no app store downloads needed!
- 🎨 **Modern Glassmorphism Dashboard**: Real-time neon audio visualizer, connection status badge, volume slider, and latency metrics.
- 📷 **QR Code Pairing**: Point smartphone camera at PC screen to connect in 1 tap.

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                      WINDOWS PC                        │
│                                                        │
│   System Audio ──► WASAPI Loopback (IAudioClient3)     │
│                           │                            │
│                  MMCSS Thread Priority                 │
│                           │                            │
│         ┌─────────────────┴─────────────────┐          │
│         ▼                                   ▼          │
│   USB (Raw PCM)                     Wi-Fi / Network    │
│   ADB Forward / Tethering           WebSocket Stream   │
└─────────┬───────────────────────────────────┬──────────┘
          │                                   │
   Local Socket                       Binary WebSocket
          │                                   │
┌─────────▼───────────────────────────────────▼──────────┐
│                    MOBILE RECEIVER                     │
│                                                        │
│             WebAudio AudioWorklet Ring Buffer          │
│                           │                            │
│                 Dynamic Drift Correction               │
│                           │                            │
│                     Phone Speaker                      │
└────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Setup & Usage

### 1. Requirements
- Windows 10 / 11 PC
- Python 3.10+
- Smartphone (Android or iOS)

### 2. Installation
Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Run WinAudio Server
Start the PC server:
```bash
python app.py
```

### 4. Connect Phone
- **USB Cable**: Plug phone via USB, enable USB Tethering or ADB Debugging, and open `http://localhost:8080` on phone browser.
- **Wi-Fi**: Open phone camera, scan the QR code printed in terminal, or browse to `http://<PC-IP>:8080`.
- **Start Audio**: Tap **"Start PC Speaker Stream"** on your phone!

---

## 🧪 Verification & Latency Test

Run the included benchmark client to test live streaming latency and throughput:
```bash
python test_client.py
```

---

## 📁 Project Structure

- `app.py`: Main launcher and PC control center.
- `server/audio_capture.py`: WASAPI loopback audio capture engine with MMCSS Pro Audio elevation.
- `server/network_server.py`: Low-latency WebSocket & HTTP streaming server.
- `server/adb_helper.py`: USB ADB port forwarding & network interface helper.
- `server/zeroconf_service.py`: mDNS Zeroconf service discovery.
- `web/`: Mobile client web app (HTML5, CSS3 Glassmorphism, WebAudio AudioWorklet).
- `test_client.py`: Automated benchmark and socket validation tool.
