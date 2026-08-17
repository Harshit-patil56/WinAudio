#!/usr/bin/env python3
"""
WinAudio - Native Windows 11 Desktop Control Center
Strictly follows Microsoft Fluent Design System & Windows 11 Design Principles.
"""
import os
import sys
import time
import io
import math
import asyncio
import threading
import logging
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw
import pystray
from pystray import MenuItem as item

from server.audio_capture import WASAPICapture
from server.network_server import WinAudioNetworkServer
from server.adb_helper import setup_adb_port_forward, get_network_ip_addresses, get_adb_device
from server.zeroconf_service import WinAudioBroadcaster

# Windows Event Loop Policy
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("WinAudio.GUI")

# ── Microsoft Windows 11 Fluent Design System Color Tokens ───────────────────
MICA_BASE_BG     = "#202020"  # Windows 11 Mica Canvas (Dark Mode)
CARD_BG         = "#2B2B2B"  # Layer 1 Surface Card
CARD_BORDER     = "#383838"  # 1px Surface Stroke
CONTROL_BG      = "#323232"  # Layer 2 Interactive Controls
CONTROL_BORDER  = "#3E3E3E"
FLUENT_ACCENT   = "#60CDFF"  # Windows 11 Accent Blue (Dark Mode)
FLUENT_ACCENT_HOVER = "#75D4FF"
FLUENT_PURPLE   = "#BF5AF2"  # Harmonic Wave 2 (Fluent Violet)
FLUENT_TEAL     = "#70FFD2"  # Harmonic Wave 3 (Mint / Shimmer)
FLUENT_RED      = "#FF99A4"  # Fluent Stop / Alert
FLUENT_RED_HOVER = "#FFAEB7"
FLUENT_GREEN    = "#6CCB5F"  # Fluent Success
TEXT_PRIMARY    = "#FFFFFF"
TEXT_SECONDARY  = "#A0A0A0"

# Fluent Geometry Standards
RADIUS_CARD    = 8   # Top-level containers & cards (8px standard)
RADIUS_CONTROL = 4   # Buttons, inputs, and controls (4px standard)
RADIUS_PILL    = 13  # Fully rounded status badge capsule

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def generate_fluent_icon(size=64):
    """Generates an authentic Fluent / Apple Hi-Fi stereo receiver icon."""
    img = Image.new('RGBA', (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Blue Squircle Background
    corner = int(size * 0.25)
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=corner, fill="#0A84FF")

    # Dual Speakers (White with blue drivers)
    pad = int(size * 0.12)
    spk_w = int(size * 0.32)
    spk_h = int(size * 0.70)
    spk_r = int(spk_w * 0.38)

    # Left Speaker
    lx0 = pad
    ly0 = int((size - spk_h) / 2)
    lx1 = lx0 + spk_w
    ly1 = ly0 + spk_h
    draw.rounded_rectangle([lx0, ly0, lx1, ly1], radius=spk_r, fill="#FFFFFF")
    
    # Tweeter & Woofer (Left)
    tw_r = int(spk_w * 0.20)
    wf_r = int(spk_w * 0.35)
    lcx = int((lx0 + lx1) / 2)
    draw.ellipse([lcx - tw_r, ly0 + int(spk_h * 0.24) - tw_r, lcx + tw_r, ly0 + int(spk_h * 0.24) + tw_r], fill="#0A84FF")
    draw.ellipse([lcx - wf_r, ly0 + int(spk_h * 0.65) - wf_r, lcx + wf_r, ly0 + int(spk_h * 0.65) + wf_r], fill="#0A84FF")
    draw.ellipse([lcx - int(wf_r * 0.5), ly0 + int(spk_h * 0.65) - int(wf_r * 0.5), lcx + int(wf_r * 0.5), ly0 + int(spk_h * 0.65) + int(wf_r * 0.5)], fill="#FFFFFF")

    # Right Speaker
    rx0 = size - pad - spk_w
    ry0 = ly0
    rx1 = rx0 + spk_w
    ry1 = ly1
    draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=spk_r, fill="#FFFFFF")

    # Tweeter & Woofer (Right)
    rcx = int((rx0 + rx1) / 2)
    draw.ellipse([rcx - tw_r, ry0 + int(spk_h * 0.24) - tw_r, rcx + tw_r, ry0 + int(spk_h * 0.24) + tw_r], fill="#0A84FF")
    draw.ellipse([rcx - wf_r, ry0 + int(spk_h * 0.65) - wf_r, rcx + wf_r, ry0 + int(spk_h * 0.65) + wf_r], fill="#0A84FF")
    draw.ellipse([rcx - int(wf_r * 0.5), ry0 + int(spk_h * 0.65) - int(wf_r * 0.5), rcx + int(wf_r * 0.5), ry0 + int(spk_h * 0.65) + int(wf_r * 0.5)], fill="#FFFFFF")

    return img

class WinAudioGUI(ctk.CTk):
    def __init__(self, port=8080):
        super().__init__()

        self.port = port
        self.web_dir = os.path.join(os.path.dirname(__file__), "web")
        
        # Audio & Server Core
        self.server = WinAudioNetworkServer(host="0.0.0.0", port=self.port, web_dir=self.web_dir)
        self.broadcaster = WinAudioBroadcaster(port=self.port, name="WinAudio-PC")
        self.audio_capture = None

        self.server_thread = None
        self.server_loop = None
        self.is_streaming = False
        self.tray_icon = None

        # ── Waveform Animation State ─────────────────────────────────────────
        self.wave_phase = 0.0
        self.current_amp = 0.05
        self.target_amp  = 0.05
        self.rolling_peak = 0.15

        # Window Setup
        self.title("WinAudio Control Center")
        self.geometry("740x590")
        self.resizable(False, False)
        self.configure(fg_color=MICA_BASE_BG)

        # Generate & Set App Icon
        self._setup_app_icon()

        # Build Fluent UI
        self._build_ui()

        # Start Server & Capture automatically
        self.start_server()

        # Start Harmonic Waveform Animation Loop (40 FPS)
        self._poll_vu_meter()

        # Handle window close (minimize to tray)
        self.protocol("WM_DELETE_WINDOW", self.on_close_window)

    def _setup_app_icon(self):
        try:
            self.icon_image = generate_fluent_icon(64)
            icon_path = os.path.join(self.web_dir, "icon.png")
            self.icon_image.save(icon_path, format="PNG")
            
            ico_path = os.path.join(self.web_dir, "favicon.ico")
            self.icon_image.save(ico_path, format="ICO", sizes=[(64, 64), (32, 32), (16, 16)])
            
            self.iconphoto(False, ImageTk.PhotoImage(self.icon_image))
        except Exception as e:
            logger.warning(f"Could not load icon: {e}")

    def on_pcm_chunk(self, data, sample_rate, channels):
        if self.server:
            self.server.broadcast_pcm(data)

    def _build_ui(self):
        # Main Padding Container
        self.main_container = ctk.CTkFrame(self, fg_color=MICA_BASE_BG, corner_radius=0)
        self.main_container.pack(fill="both", expand=True, padx=16, pady=14)

        # ── Header Bar ───────────────────────────────────────────────────────
        self.header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.header_frame.pack(fill="x", pady=(0, 10))

        self.title_lbl = ctk.CTkLabel(
            self.header_frame,
            text="WinAudio Receiver",
            font=ctk.CTkFont(family="Segoe UI Variable Display", size=19, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        self.title_lbl.pack(side="left")

        # Fully Rounded Status Pill Badge (Radius 13px)
        self.status_pill = ctk.CTkFrame(
            self.header_frame,
            fg_color="#1A3B22",
            corner_radius=RADIUS_PILL,
            border_width=1,
            border_color="#2D6638"
        )
        self.status_pill.pack(side="right")

        self.status_dot_lbl = ctk.CTkLabel(
            self.status_pill,
            text="● Active on Port 8080",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"),
            text_color=FLUENT_GREEN,
            padx=12,
            pady=4
        )
        self.status_dot_lbl.pack()

        # ── Two-Column Layout (QR Card on Left, Details on Right) ─────────────
        self.content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

        # Left: QR Code Card
        self.qr_card = ctk.CTkFrame(
            self.content_frame,
            width=260,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
            border_width=1,
            corner_radius=RADIUS_CARD
        )
        self.qr_card.pack(side="left", fill="y", padx=(0, 10), pady=0)
        self.qr_card.pack_propagate(False)

        self.qr_title = ctk.CTkLabel(
            self.qr_card,
            text="Scan with Phone Camera",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=13, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        self.qr_title.pack(pady=(12, 4))

        self.qr_canvas = ctk.CTkLabel(self.qr_card, text="", fg_color="transparent")
        self.qr_canvas.pack(pady=2)

        # Inset Card: Real-time Connection Mode (USB vs Wi-Fi Detection)
        self.mode_status_card = ctk.CTkFrame(
            self.qr_card,
            fg_color="#202020",
            border_color="#383838",
            border_width=1,
            corner_radius=RADIUS_CONTROL
        )
        self.mode_status_card.pack(fill="x", padx=12, pady=(6, 10))

        self.mode_icon_lbl = ctk.CTkLabel(
            self.mode_status_card,
            text="● Waiting for Connection",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"),
            text_color=TEXT_SECONDARY
        )
        self.mode_icon_lbl.pack(pady=(6, 1))

        self.mode_detail_lbl = ctk.CTkLabel(
            self.mode_status_card,
            text="Scan QR or open link on phone",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=10),
            text_color=TEXT_SECONDARY
        )
        self.mode_detail_lbl.pack(pady=(0, 6))

        # Right: Info & Settings Column
        self.right_col = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.right_col.pack(side="right", fill="both", expand=True)

        # ── Card 1: Connection Endpoints ─────────────────────────────────────
        self.conn_card = ctk.CTkFrame(
            self.right_col,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
            border_width=1,
            corner_radius=RADIUS_CARD
        )
        self.conn_card.pack(fill="x", pady=(0, 10), padx=0)

        self.conn_hdr = ctk.CTkLabel(
            self.conn_card,
            text="Connection Addresses",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=13, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        self.conn_hdr.pack(anchor="w", padx=14, pady=(10, 6))

        # Network IP (Wi-Fi / LAN) Link Row
        self.wifi_row = ctk.CTkFrame(self.conn_card, fg_color="transparent")
        self.wifi_row.pack(fill="x", padx=14, pady=3)

        self.wifi_lbl = ctk.CTkLabel(self.wifi_row, text="Network IP:", font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"), text_color=FLUENT_ACCENT, width=80, anchor="w")
        self.wifi_lbl.pack(side="left")

        self.wifi_url_lbl = ctk.CTkLabel(self.wifi_row, text="http://192.168.0.101:8080", font=ctk.CTkFont(family="Segoe UI Variable Text", size=11), text_color=TEXT_PRIMARY, anchor="w")
        self.wifi_url_lbl.pack(side="left", fill="x", expand=True)

        self.copy_wifi_btn = ctk.CTkButton(
            self.wifi_row,
            text="Copy",
            width=54,
            height=26,
            corner_radius=RADIUS_CONTROL,
            fg_color=CONTROL_BG,
            border_color=CONTROL_BORDER,
            border_width=1,
            hover_color="#444444",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            command=self._copy_wifi_url
        )
        self.copy_wifi_btn.pack(side="right", padx=(4, 0))

        # Localhost (USB / Direct) Link Row
        self.usb_row = ctk.CTkFrame(self.conn_card, fg_color="transparent")
        self.usb_row.pack(fill="x", padx=14, pady=(3, 10))

        self.usb_lbl = ctk.CTkLabel(self.usb_row, text="Localhost:", font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"), text_color="#30D158", width=80, anchor="w")
        self.usb_lbl.pack(side="left")

        self.usb_url_lbl = ctk.CTkLabel(self.usb_row, text="http://localhost:8080", font=ctk.CTkFont(family="Segoe UI Variable Text", size=11), text_color=TEXT_PRIMARY, anchor="w")
        self.usb_url_lbl.pack(side="left", fill="x", expand=True)

        self.copy_usb_btn = ctk.CTkButton(
            self.usb_row,
            text="Copy",
            width=54,
            height=26,
            corner_radius=RADIUS_CONTROL,
            fg_color=CONTROL_BG,
            border_color=CONTROL_BORDER,
            border_width=1,
            hover_color="#444444",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            command=self._copy_usb_url
        )
        self.copy_usb_btn.pack(side="right", padx=(4, 0))

        # ── Card 2: Audio Device & Transmission Quality ──────────────────────
        self.audio_card = ctk.CTkFrame(
            self.right_col,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
            border_width=1,
            corner_radius=RADIUS_CARD
        )
        self.audio_card.pack(fill="both", expand=True, padx=0, pady=0)

        self.audio_hdr = ctk.CTkLabel(
            self.audio_card,
            text="Audio Source & Transmission Quality",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=13, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        self.audio_hdr.pack(anchor="w", padx=14, pady=(10, 4))

        self.device_lbl = ctk.CTkLabel(
            self.audio_card,
            text="Capture Device: Realtek(R) Audio [Loopback]",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_SECONDARY
        )
        self.device_lbl.pack(anchor="w", padx=14, pady=(0, 6))

        # Transmission Quality Radio Buttons
        self.quality_var = tk.StringVar(value="pcm16")

        self.rad_pcm16 = ctk.CTkRadioButton(
            self.audio_card,
            text="Bit-Perfect 48kHz Stereo PCM (1.5 Mbps - Recommended)",
            variable=self.quality_var,
            value="pcm16",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_PRIMARY,
            fg_color=FLUENT_ACCENT,
            radiobutton_width=16,
            radiobutton_height=16
        )
        self.rad_pcm16.pack(anchor="w", padx=14, pady=2)

        self.rad_opus = ctk.CTkRadioButton(
            self.audio_card,
            text="Compressed Opus 48kHz (256 kbps - Weak Wi-Fi Networks)",
            variable=self.quality_var,
            value="opus",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_PRIMARY,
            fg_color=FLUENT_ACCENT,
            radiobutton_width=16,
            radiobutton_height=16
        )
        self.rad_opus.pack(anchor="w", padx=14, pady=2)

        # ── Dynamic Multi-Harmonic Acoustic Waveform Canvas ──────────────────
        self.vu_frame = ctk.CTkFrame(self.audio_card, fg_color="transparent")
        self.vu_frame.pack(fill="x", padx=14, pady=(8, 10))

        self.vu_hdr_lbl = ctk.CTkLabel(
            self.vu_frame,
            text="Live Audio Waveform Activity:",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_SECONDARY
        )
        self.vu_hdr_lbl.pack(anchor="w", pady=(0, 4))

        # Dark Canvas for Harmonic Sine Waves
        self.vu_canvas = tk.Canvas(
            self.vu_frame,
            height=46,
            bg="#1E1E20",
            highlightthickness=1,
            highlightbackground="#363638"
        )
        self.vu_canvas.pack(fill="x")

        # ── Bottom Action Toolbar ─────────────────────────────────────────────
        self.toolbar_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.toolbar_frame.pack(fill="x", pady=(12, 0))

        self.toggle_btn = ctk.CTkButton(
            self.toolbar_frame,
            text="Stop Server",
            fg_color=FLUENT_RED,
            hover_color=FLUENT_RED_HOVER,
            text_color="#000000",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=12, weight="bold"),
            height=32,
            corner_radius=RADIUS_CONTROL,
            command=self.toggle_server
        )
        self.toggle_btn.pack(side="left", padx=(0, 8))

        self.tray_btn = ctk.CTkButton(
            self.toolbar_frame,
            text="Minimize to System Tray",
            fg_color=CONTROL_BG,
            border_color=CONTROL_BORDER,
            border_width=1,
            hover_color="#444444",
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=12),
            height=32,
            corner_radius=RADIUS_CONTROL,
            command=self.minimize_to_tray
        )
        self.tray_btn.pack(side="left")

        # ── ADB USB Status Row (Live Indicator) ──────────────────────────────
        self.adb_row = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.adb_row.pack(fill="x", pady=(6, 0))

        self.adb_badge = ctk.CTkFrame(
            self.adb_row,
            fg_color="#2A2A2A",
            border_color="#3A3A3A",
            border_width=1,
            corner_radius=RADIUS_PILL
        )
        self.adb_badge.pack(side="left")

        self.adb_lbl = ctk.CTkLabel(
            self.adb_badge,
            text="⬤  USB (ADB): Checking...",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_SECONDARY,
            padx=12,
            pady=4
        )
        self.adb_lbl.pack()

        self.adb_hint = ctk.CTkLabel(
            self.adb_row,
            text="Plug in phone + enable USB Debugging to use ADB tunnel",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=10),
            text_color="#666666"
        )
        self.adb_hint.pack(side="left", padx=(10, 0))

        # Start live ADB polling (every 3 seconds)
        self._poll_adb_status()

    def _copy_wifi_url(self):
        url = self.wifi_url_lbl.cget("text")
        self.clipboard_clear()
        self.clipboard_append(url)
        self.copy_wifi_btn.configure(text="Copied!")
        self.after(1500, lambda: self.copy_wifi_btn.configure(text="Copy"))

    def _copy_usb_url(self):
        url = self.usb_url_lbl.cget("text")
        self.clipboard_clear()
        self.clipboard_append(url)
        self.copy_usb_btn.configure(text="Copied!")
        self.after(1500, lambda: self.copy_usb_btn.configure(text="Copy"))

    def _update_qr_and_urls(self):
        ip_addresses = get_network_ip_addresses()
        primary_ip = ip_addresses[0]['ip'] if ip_addresses else '127.0.0.1'
        mobile_url = f"http://{primary_ip}:{self.port}"
        usb_url = f"http://localhost:{self.port}"

        self.wifi_url_lbl.configure(text=mobile_url)
        self.usb_url_lbl.configure(text=usb_url)
        self.status_dot_lbl.configure(text=f"● Active on Port {self.port}")

        # Render QR Code Image
        qr_bytes = self.server.generate_qr_code(mobile_url)
        pil_img = Image.open(io.BytesIO(qr_bytes)).resize((180, 180), Image.Resampling.NEAREST)
        self.qr_image_tk = ImageTk.PhotoImage(pil_img)
        self.qr_canvas.configure(image=self.qr_image_tk)

    def start_server(self):
        if self.is_streaming:
            return

        self.port = self.server.prepare_port()
        self.broadcaster.port = self.port

        # 1. Setup WASAPI Loopback Capture
        self.audio_capture = WASAPICapture(
            sample_rate=48000,
            channels=2,
            frames_per_buffer=256,
            on_audio_chunk=self.on_pcm_chunk
        )
        self.audio_capture.start()
        self.device_lbl.configure(text=f"Capture Device: {self.audio_capture.device_name}")

        # 2. Setup ADB USB Port Forwarding
        setup_adb_port_forward(port=self.port)

        # 3. Start Zeroconf mDNS
        self.broadcaster.start()

        # 4. Start Server Async Loop in Background Thread
        def run_async_server():
            self.server_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.server_loop)
            self.server_loop.run_until_complete(self.server.run_server())

        self.server_thread = threading.Thread(target=run_async_server, daemon=True)
        self.server_thread.start()

        self.is_streaming = True
        self.toggle_btn.configure(text="Stop Server", fg_color=FLUENT_RED, hover_color=FLUENT_RED_HOVER)
        self.status_pill.configure(fg_color="#1A3B22", border_color="#2D6638")
        self.status_dot_lbl.configure(text=f"● Active on Port {self.port}", text_color=FLUENT_GREEN)
        # Delay QR + URL update slightly so the server loop is fully ready
        self.after(800, self._update_qr_and_urls)

    def stop_server(self):
        if not self.is_streaming:
            return

        if self.audio_capture:
            self.audio_capture.stop()
            self.audio_capture = None

        if self.broadcaster:
            self.broadcaster.stop()

        if self.server and self.server_loop:
            asyncio.run_coroutine_threadsafe(self.server.cleanup(), self.server_loop)

        self.is_streaming = False
        self.toggle_btn.configure(text="Start Server", fg_color=FLUENT_ACCENT, hover_color=FLUENT_ACCENT_HOVER)
        self.status_pill.configure(fg_color="#2A2A2A", border_color="#3E3E3E")
        self.status_dot_lbl.configure(text="● Stopped", text_color=TEXT_SECONDARY)

    def toggle_server(self):
        if self.is_streaming:
            self.stop_server()
        else:
            self.start_server()

    # ── Live ADB USB Device Status Polling (every 3 seconds) ─────────────────
    def _poll_adb_status(self):
        def _check():
            adb_bin, device_id = get_adb_device()
            self.after(0, self._update_adb_badge, adb_bin, device_id)

        # Run in background thread so it doesn't block the GUI
        threading.Thread(target=_check, daemon=True).start()
        self.after(3000, self._poll_adb_status)

    def _update_adb_badge(self, adb_bin, device_id):
        if not adb_bin:
            self.adb_badge.configure(fg_color="#2A2A2A", border_color="#3A3A3A")
            self.adb_lbl.configure(
                text="⬤  USB (ADB): Not installed",
                text_color="#666666"
            )
            self.adb_hint.configure(text="Install Android Platform Tools and add to PATH")
        elif not device_id:
            self.adb_badge.configure(fg_color="#2A2A2A", border_color="#3A3A3A")
            self.adb_lbl.configure(
                text="⬤  USB (ADB): No device",
                text_color="#666666"
            )
            self.adb_hint.configure(text="Plug in phone + enable USB Debugging  →  open http://localhost on phone")
        else:
            self.adb_badge.configure(fg_color="#142B1A", border_color="#24542E")
            self.adb_lbl.configure(
                text=f"⬤  USB (ADB): {device_id} connected",
                text_color="#30D158"
            )
            self.adb_hint.configure(text="Open http://localhost on phone Chrome to use USB tunnel")

    # ── Multi-Harmonic Acoustic Sine Waveform Animation Engine ────────────────
    def _poll_vu_meter(self):
        self.wave_phase += 0.12
        if self.wave_phase > 2000.0:
            self.wave_phase = 0.0

        if self.is_streaming and self.audio_capture:
            peak = getattr(self.audio_capture, 'current_peak', 0.0)
            # Dynamic AGC Peak Normalization
            self.rolling_peak = max(peak * 1.25, self.rolling_peak * 0.985, 0.06)
            normalized = min(1.0, max(0.0, peak / self.rolling_peak))
            self.target_amp = min(0.92, max(0.06, math.pow(normalized, 1.25)))
        else:
            # Ambient gentle breathing
            self.target_amp = 0.08 + math.sin(time.time() * 2.5) * 0.03

        # Fluid Spring Lerp (Fast Attack, Smooth Decay)
        is_attacking = self.target_amp > self.current_amp
        lerp = 0.38 if is_attacking else 0.16
        self.current_amp += (self.target_amp - self.current_amp) * lerp

        # Render Multi-Harmonic Splines on Canvas
        self.vu_canvas.delete("all")
        cw = self.vu_canvas.winfo_width()
        ch = self.vu_canvas.winfo_height()

        if cw > 40 and ch > 15:
            cy = ch / 2.0
            max_h = (ch / 2.0) - 3.0
            amp = self.current_amp * max_h

            num_pts = 60
            pts_main = []
            pts_harm2 = []
            pts_harm3 = []

            for i in range(num_pts + 1):
                x = (i / num_pts) * cw
                # Hanning Window Envelope (pinches ends smoothly, expands center)
                env = math.sin((i / num_pts) * math.pi) ** 1.35

                # Wave 1 (Primary Energy: Fluent Cyan / Blue)
                y1 = cy + math.sin((i / num_pts) * 4.0 * math.pi - self.wave_phase) * amp * env
                pts_main.extend([x, y1])

                # Wave 2 (Harmonic 2: Violet / Purple)
                y2 = cy + math.sin((i / num_pts) * 6.5 * math.pi + self.wave_phase * 1.4) * (amp * 0.62) * env
                pts_harm2.extend([x, y2])

                # Wave 3 (Harmonic 3: Mint / Shimmer)
                y3 = cy + math.sin((i / num_pts) * 9.0 * math.pi - self.wave_phase * 1.9) * (amp * 0.32) * env
                pts_harm3.extend([x, y3])

            # Draw smooth spline waves with layering
            if len(pts_harm2) >= 4:
                self.vu_canvas.create_line(pts_harm2, fill="#7B42BC", width=1.5, smooth=True)
            if len(pts_harm3) >= 4:
                self.vu_canvas.create_line(pts_harm3, fill="#38A888", width=1.2, smooth=True)
        # Update Live Connection Mode Badge (USB vs Network IP)
        if self.is_streaming and self.server:
            conn_mode, conn_ip = self.server.get_connection_status()
            if conn_mode == "usb":
                self.mode_status_card.configure(fg_color="#142B1A", border_color="#24542E")
                self.mode_icon_lbl.configure(text="🔌 Connected: USB (Localhost)", text_color="#30D158")
                self.mode_detail_lbl.configure(text="ADB Reverse Tethering · Ultra-Low Latency", text_color="#A8F5B8")
            elif conn_mode == "wifi":
                self.mode_status_card.configure(fg_color="#142638", border_color="#1E4B70")
                self.mode_icon_lbl.configure(text=f"📶 Connected: Network ({conn_ip})", text_color=FLUENT_ACCENT)
                self.mode_detail_lbl.configure(text="Local Wi-Fi Stream · Dynamic Buffer", text_color="#B5E4FF")
            else:
                self.mode_status_card.configure(fg_color="#202020", border_color="#383838")
                self.mode_icon_lbl.configure(text="● Waiting for Connection", text_color=TEXT_SECONDARY)
                self.mode_detail_lbl.configure(text="Scan QR or open link on phone", text_color=TEXT_SECONDARY)
        else:
            self.mode_status_card.configure(fg_color="#202020", border_color="#383838")
            self.mode_icon_lbl.configure(text="● Server Stopped", text_color=TEXT_SECONDARY)
            self.mode_detail_lbl.configure(text="Click 'Start Server' below", text_color=TEXT_SECONDARY)

        self.after(25, self._poll_vu_meter)  # ~40 FPS smooth sinusoidal wave

    # ── System Tray Integration ──────────────────────────────────────────────
    def minimize_to_tray(self):
        self.withdraw()
        self._create_tray_icon()

    def _create_tray_icon(self):
        if self.tray_icon:
            return

        tray_image = generate_fluent_icon(64)

        menu = pystray.Menu(
            item('Open WinAudio Control Center', self._restore_from_tray, default=True),
            item('Copy Network Link', self._copy_wifi_url),
            item('Copy Localhost Link', self._copy_usb_url),
            item('Stop / Start Server', self.toggle_server),
            pystray.Menu.SEPARATOR,
            item('Exit', self._quit_app)
        )

        self.tray_icon = pystray.Icon("WinAudio", tray_image, "WinAudio Receiver", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _restore_from_tray(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.after(0, self.deiconify)

    def on_close_window(self):
        self.minimize_to_tray()

    def _quit_app(self, icon=None, item=None):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self.stop_server()
        try:
            self.after(0, self.destroy)
        except Exception:
            pass

if __name__ == "__main__":
    app = WinAudioGUI()
    app.mainloop()
