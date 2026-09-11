#!/usr/bin/env python3
"""
WinAudio - Ultra-Low Latency Smartphone PC Speaker Server
Converts your phone into a high-quality, zero-lag external speaker over USB or Wi-Fi.
"""
import os
import sys
import time
import asyncio
import threading
import logging
from server.audio_capture import WASAPICapture
from server.network_server import WinAudioNetworkServer
from server.adb_helper import setup_adb_port_forward, get_network_ip_addresses
from server.zeroconf_service import WinAudioBroadcaster

# Fix: Windows ProactorEventLoop (IOCP) raises WinError 59 on abrupt client
# disconnect and on USB RNDIS interface drops. SelectorEventLoop is stable
# for our WebSocket server use case.
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("WinAudio.App")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

class WinAudioApp:
    def __init__(self, port=8080):
        self.port = port
        self.web_dir = os.path.join(os.path.dirname(__file__), "web")
        
        self.server = WinAudioNetworkServer(host="0.0.0.0", port=self.port, web_dir=self.web_dir)
        self.broadcaster = WinAudioBroadcaster(port=self.port, name="WinAudio-PC")
        self.audio_capture = None

        self.is_running = False
        self.server_thread = None

    def on_pcm_chunk(self, data, sample_rate, channels):
        """Called whenever WASAPI captures an audio buffer."""
        if self.server:
            self.server.broadcast_pcm(data)

    def start(self):
        logger.info("Initializing WinAudio PC Server Suite...")
        
        # 0. Resolve free port dynamically
        self.port = self.server.prepare_port()
        self.broadcaster.port = self.port

        # 1. Setup WASAPI Audio Loopback
        self.audio_capture = WASAPICapture(
            sample_rate=48000,
            channels=2,
            frames_per_buffer=512, # ~10.7ms buffer
            on_audio_chunk=self.on_pcm_chunk
        )
        self.audio_capture.start()

        # 2. Setup ADB USB Port Forwarding
        adb_ok, adb_msg = setup_adb_port_forward(port=self.port)
        
        # 3. Start mDNS Zeroconf
        self.broadcaster.start()

        # 4. Print Dashboard Banner
        ip_addresses = get_network_ip_addresses()
        primary_ip = ip_addresses[0]['ip'] if ip_addresses else '127.0.0.1'
        mobile_url = f"http://{primary_ip}:{self.port}"
        usb_url = f"http://localhost:{self.port}"

        print("\n" + "=" * 65)
        print("                [WINAUDIO PC SPEAKER SERVER]")
        print("   Transform your smartphone into a low-latency PC Speaker!")
        print("=" * 65)
        print(f" [Audio Device] : {self.audio_capture.device_name}")
        print(f" [Audio Format] : {self.audio_capture.actual_sample_rate} Hz | {self.audio_capture.actual_channels} Channels | 5.3ms Buffer")

        print(f" [USB ADB Mode] : {'[ACTIVE]' if adb_ok else '[STANDBY]'} - {adb_msg}")
        print("-" * 65)
        print(" [MOBILE CONNECTION METHODS]:")
        print(f"   1. USB Cable (Lowest Latency):  Open {usb_url} on phone")
        print(f"   2. Wi-Fi / Local Network:       Open {mobile_url} on phone")
        for net in ip_addresses:
            print(f"      -> http://{net['ip']}:{self.port} ({net['type']})")
        print("-" * 65)
        print(" [SCAN THIS QR CODE WITH YOUR PHONE CAMERA TO CONNECT]:")

        try:
            ascii_qr = self.server.generate_ascii_qr(mobile_url)
            print(ascii_qr)
        except Exception:
            pass
        print("=" * 65 + "\n")

        # 5. Start Server Event Loop in Background Thread
        self.is_running = True
        def run_loop():
            while self.is_running:
                try:
                    asyncio.run(self.server.run_server())
                except OSError as e:
                    if self.is_running:
                        logger.warning(f"Server loop OSError (likely network drop): {e} — restarting in 1s")
                        time.sleep(1)
                except Exception as e:
                    if self.is_running:
                        logger.error(f"Server loop error: {e} — restarting in 1s")
                        time.sleep(1)
                    else:
                        break

        self.server_thread = threading.Thread(target=run_loop, daemon=True, name="WinAudio-ServerLoop")
        self.server_thread.start()


    def stop(self):
        logger.info("Shutting down WinAudio App...")
        self.is_running = False
        if self.audio_capture:
            self.audio_capture.stop()
        if self.broadcaster:
            self.broadcaster.stop()
        logger.info("WinAudio App successfully stopped.")

if __name__ == "__main__":
    app = WinAudioApp(port=8080)
    try:
        app.start()
        print("Server running! Press Ctrl+C to stop.\n")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
        app.stop()
        sys.exit(0)
