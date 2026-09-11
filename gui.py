#!/usr/bin/env python3
"""
WinAudio - Windows 11 Fluent Design System (WinUI 3) Desktop Control Center
Crafted with Windows 11 Dark Mode Aesthetics, Dynamic Multi-Harmonic Visualizer,
WinUI 3 Segmented QR Code Controls (Wi-Fi Network vs USB Localhost), and Persistent System Tray.
"""
import os
import sys
import time
import io
import math
import asyncio
import threading
import multiprocessing
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

# ── Windows 11 Fluent Design System (WinUI 3) Tokens ─────────────────────────
MICA_BG          = "#202020"  # Windows 11 Dark Mode Canvas (Mica Base)
CARD_BG          = "#2B2B2B"  # WinUI 3 Layer 1 Card Surface
CARD_BORDER      = "#383838"  # 1px Subtle Surface Stroke
CONTROL_BG       = "#2F2F2F"  # WinUI 3 Standard Button (Rest)
CONTROL_BORDER   = "#3D3D3D"  # WinUI 3 Button Stroke
CONTROL_HOVER    = "#383838"  # WinUI 3 Standard Button (Hover)

# WinUI 3 Accent Colors (Dark Mode)
WIN_ACCENT       = "#60CDFF"  # Windows 11 Accent Blue (Dark Mode)
WIN_ACCENT_HOVER = "#75D4FF"  # Windows 11 Accent Hover
WIN_ACCENT_TEXT  = "#000000"  # WinUI 3 Design Kit: Black text on Accent Blue
WIN_DANGER       = "#C42B1C"  # Windows 11 Critical / Stop Button
WIN_DANGER_HOVER = "#D83B01"
WIN_SUCCESS      = "#6CCB5F"  # Windows 11 Green
WIN_PURPLE       = "#BF5AF2"  # Visualizer Harmonic 2
WIN_TEAL         = "#70FFD2"  # Visualizer Harmonic 3

TEXT_PRIMARY     = "#FFFFFF"  # Primary Label
TEXT_SECONDARY   = "#A0A0A0"  # Secondary Label
TEXT_TERTIARY    = "#707070"  # Tertiary Label

# WinUI 3 Geometry Standards
RADIUS_CARD    = 8   # Windows 11 Card Radius (8px standard)
RADIUS_CONTROL = 4   # Windows 11 Buttons, Inputs & Controls (strictly 4px)
RADIUS_PILL    = 12  # Windows 11 InfoBadge Capsule

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def generate_fluent_icon(size=64):
    """Generates an authentic Windows 11 Fluent stereo receiver icon."""
    img = Image.new('RGBA', (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Windows 11 Squircle Background
    corner = int(size * 0.24)
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=corner, fill="#0078D4")

    # Dual Speakers (Pure White enclosures with Fluent Blue drivers)
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
    draw.ellipse([lcx - tw_r, ly0 + int(spk_h * 0.24) - tw_r, lcx + tw_r, ly0 + int(spk_h * 0.24) + tw_r], fill="#0078D4")
    draw.ellipse([lcx - wf_r, ly0 + int(spk_h * 0.65) - wf_r, lcx + wf_r, ly0 + int(spk_h * 0.65) + wf_r], fill="#0078D4")
    draw.ellipse([lcx - int(wf_r * 0.5), ly0 + int(spk_h * 0.65) - int(wf_r * 0.5), lcx + int(wf_r * 0.5), ly0 + int(spk_h * 0.65) + int(wf_r * 0.5)], fill="#FFFFFF")

    # Right Speaker
    rx0 = size - pad - spk_w
    ry0 = ly0
    rx1 = rx0 + spk_w
    ry1 = ly1
    draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=spk_r, fill="#FFFFFF")

    # Tweeter & Woofer (Right)
    rcx = int((rx0 + rx1) / 2)
    draw.ellipse([rcx - tw_r, ry0 + int(spk_h * 0.24) - tw_r, rcx + tw_r, ry0 + int(spk_h * 0.24) + tw_r], fill="#0078D4")
    draw.ellipse([rcx - wf_r, ry0 + int(spk_h * 0.65) - wf_r, rcx + wf_r, ry0 + int(spk_h * 0.65) + wf_r], fill="#0078D4")
    draw.ellipse([rcx - int(wf_r * 0.5), ry0 + int(spk_h * 0.65) - int(wf_r * 0.5), rcx + int(wf_r * 0.5), ry0 + int(spk_h * 0.65) + int(wf_r * 0.5)], fill="#FFFFFF")

    return img

class WinAudioGUI(ctk.CTk):
    def __init__(self, port=8080):
        super().__init__()
        self.port = port
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            self.web_dir = os.path.join(sys._MEIPASS, "web")
        else:
            self.web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        
        # Audio & Server Core
        self.server = WinAudioNetworkServer(host="0.0.0.0", port=self.port, web_dir=self.web_dir)
        self.broadcaster = WinAudioBroadcaster(port=self.port, name="WinAudio-PC")
        self.audio_capture = None

        self.server_thread = None
        self.server_loop = None
        self.is_streaming = False
        self.tray_icon = None

        # QR Mode & URLs
        self.qr_mode = "wifi"  # "wifi" or "usb"
        self.mobile_url = f"http://127.0.0.1:{self.port}"
        self.usb_url = f"http://localhost:{self.port}"

        # ── Waveform Animation State ─────────────────────────────────────────
        self.wave_phase = 0.0
        self.current_amp = 0.05
        self.target_amp  = 0.05
        self.rolling_peak = 0.15

        # Window Setup (Windows 11 Fluent Sizing & Spacing)
        self.title("WinAudio Control Center")
        self.geometry("770x620")
        self.resizable(False, False)
        self.configure(fg_color=MICA_BG)

        # Generate & Set App Icon
        self._setup_app_icon()

        # Build Fluent UI
        self._build_ui()

        # Handle window close (minimize to system tray)
        self.protocol("WM_DELETE_WINDOW", self.on_close_window)

        # Schedule background tasks after Tkinter mainloop is active
        self.after(100, self._init_tray_icon)
        self.after(200, self.start_server)
        self.after(400, self._poll_vu_meter)
        self.after(600, self._poll_adb_status)

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
        self.main_container = ctk.CTkFrame(self, fg_color=MICA_BG, corner_radius=0)
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

        # Windows 11 InfoBadge Status Pill
        self.status_pill = ctk.CTkFrame(
            self.header_frame,
            fg_color="#102B19",
            corner_radius=RADIUS_PILL,
            border_width=1,
            border_color="#1B4A2B"
        )
        self.status_pill.pack(side="right")

        self.status_dot_lbl = ctk.CTkLabel(
            self.status_pill,
            text="● Active on Port 8080",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"),
            text_color=WIN_SUCCESS,
            padx=12,
            pady=4
        )
        self.status_dot_lbl.pack()

        # ── Two-Column Layout (QR Card on Left, Details on Right) ─────────────
        self.content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

        # Left: QR Code Card (WinUI 3 Layer 1 Card)
        self.qr_card = ctk.CTkFrame(
            self.content_frame,
            width=285,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
            border_width=1,
            corner_radius=RADIUS_CARD
        )
        self.qr_card.pack(side="left", fill="y", padx=(0, 12), pady=0)
        self.qr_card.pack_propagate(False)

        self.qr_title = ctk.CTkLabel(
            self.qr_card,
            text="Scan with Phone Camera",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=13, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        self.qr_title.pack(pady=(12, 4))

        self.qr_canvas = ctk.CTkLabel(self.qr_card, text="", fg_color="transparent")
        self.qr_canvas.pack(pady=(0, 4))

        # ── Windows 11 Segmented QR Toggle Buttons ───────────────────────────
        self.qr_toggle_frame = ctk.CTkFrame(self.qr_card, fg_color="transparent")
        self.qr_toggle_frame.pack(fill="x", padx=14, pady=(4, 8))

        self.qr_btn_wifi = ctk.CTkButton(
            self.qr_toggle_frame,
            text="Wi-Fi (Network)",
            fg_color=WIN_ACCENT,
            hover_color=WIN_ACCENT_HOVER,
            text_color=WIN_ACCENT_TEXT,
            border_width=0,
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"),
            height=30,
            corner_radius=RADIUS_CONTROL,
            command=lambda: self._set_qr_mode("wifi")
        )
        self.qr_btn_wifi.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.qr_btn_usb = ctk.CTkButton(
            self.qr_toggle_frame,
            text="USB (Localhost)",
            fg_color=CONTROL_BG,
            hover_color=CONTROL_HOVER,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=CONTROL_BORDER,
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            height=30,
            corner_radius=RADIUS_CONTROL,
            command=lambda: self._set_qr_mode("usb")
        )
        self.qr_btn_usb.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Inset Card: Real-time Connection Mode (Live Detection)
        self.mode_status_card = ctk.CTkFrame(
            self.qr_card,
            fg_color="#202020",
            border_color=CARD_BORDER,
            border_width=1,
            corner_radius=RADIUS_CONTROL
        )
        self.mode_status_card.pack(fill="x", padx=14, pady=(2, 10))

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

        # ── Card 1: Connection Endpoints (WinUI 3 Layer 1 Card) ───────────────
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
        self.conn_hdr.pack(anchor="w", padx=16, pady=(10, 6))

        # Network IP (Wi-Fi / LAN) Link Row
        self.wifi_row = ctk.CTkFrame(self.conn_card, fg_color="transparent")
        self.wifi_row.pack(fill="x", padx=16, pady=3)

        self.wifi_lbl = ctk.CTkLabel(
            self.wifi_row,
            text="Network IP:",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"),
            text_color=WIN_ACCENT,
            width=80,
            anchor="w"
        )
        self.wifi_lbl.pack(side="left")

        self.wifi_url_lbl = ctk.CTkLabel(
            self.wifi_row,
            text="http://192.168.0.101:8080",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_PRIMARY,
            anchor="w"
        )
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
            hover_color=CONTROL_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            command=self._copy_wifi_url
        )
        self.copy_wifi_btn.pack(side="right", padx=(4, 0))

        # Localhost (USB / Direct) Link Row
        self.usb_row = ctk.CTkFrame(self.conn_card, fg_color="transparent")
        self.usb_row.pack(fill="x", padx=16, pady=(3, 10))

        self.usb_lbl = ctk.CTkLabel(
            self.usb_row,
            text="Localhost:",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold"),
            text_color=WIN_SUCCESS,
            width=80,
            anchor="w"
        )
        self.usb_lbl.pack(side="left")

        self.usb_url_lbl = ctk.CTkLabel(
            self.usb_row,
            text="http://localhost:8080",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_PRIMARY,
            anchor="w"
        )
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
            hover_color=CONTROL_HOVER,
            text_color=TEXT_PRIMARY,
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
        self.audio_hdr.pack(anchor="w", padx=16, pady=(10, 4))

        self.device_lbl = ctk.CTkLabel(
            self.audio_card,
            text="Capture Device: Realtek(R) Audio [Loopback]",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_SECONDARY
        )
        self.device_lbl.pack(anchor="w", padx=16, pady=(0, 6))

        # Transmission Quality Radio Buttons
        self.quality_var = tk.StringVar(value="pcm16")

        self.rad_pcm16 = ctk.CTkRadioButton(
            self.audio_card,
            text="Bit-Perfect 48kHz Stereo PCM (1.5 Mbps - Recommended)",
            variable=self.quality_var,
            value="pcm16",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_PRIMARY,
            fg_color=WIN_ACCENT,
            border_color=CONTROL_BORDER,
            radiobutton_width=16,
            radiobutton_height=16
        )
        self.rad_pcm16.pack(anchor="w", padx=16, pady=2)

        self.rad_opus = ctk.CTkRadioButton(
            self.audio_card,
            text="Compressed Opus 48kHz (256 kbps - Weak Wi-Fi Networks)",
            variable=self.quality_var,
            value="opus",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_PRIMARY,
            fg_color=WIN_ACCENT,
            border_color=CONTROL_BORDER,
            radiobutton_width=16,
            radiobutton_height=16
        )
        self.rad_opus.pack(anchor="w", padx=16, pady=2)

        # ── Dynamic Multi-Harmonic Acoustic Waveform Canvas ──────────────────
        self.vu_frame = ctk.CTkFrame(self.audio_card, fg_color="transparent")
        self.vu_frame.pack(fill="x", padx=16, pady=(8, 12))

        self.vu_hdr_lbl = ctk.CTkLabel(
            self.vu_frame,
            text="Live Audio Waveform Activity:",
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=11),
            text_color=TEXT_SECONDARY
        )
        self.vu_hdr_lbl.pack(anchor="w", pady=(0, 4))

        # Windows 11 Dark Canvas for Multi-Harmonic Splines
        self.vu_canvas = tk.Canvas(
            self.vu_frame,
            height=46,
            bg="#1E1E20",
            highlightthickness=1,
            highlightbackground=CARD_BORDER
        )
        self.vu_canvas.pack(fill="x")

        # ── Bottom Action Toolbar ─────────────────────────────────────────────
        self.toolbar_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.toolbar_frame.pack(fill="x", pady=(12, 0))

        self.toggle_btn = ctk.CTkButton(
            self.toolbar_frame,
            text="Stop Server",
            fg_color=WIN_DANGER,
            hover_color=WIN_DANGER_HOVER,
            text_color="#FFFFFF",
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
            hover_color=CONTROL_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI Variable Text", size=12),
            height=32,
            corner_radius=RADIUS_CONTROL,
            command=self.minimize_to_tray
        )
        self.tray_btn.pack(side="left")

        # ── ADB USB Status Row (Live Indicator) ──────────────────────────────
        self.adb_row = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.adb_row.pack(fill="x", pady=(8, 0))

        self.adb_badge = ctk.CTkFrame(
            self.adb_row,
            fg_color=CARD_BG,
            border_color=CARD_BORDER,
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
            text_color=TEXT_TERTIARY
        )
        self.adb_hint.pack(side="left", padx=(10, 0))

    def _set_qr_mode(self, mode):
        """Switches between Wi-Fi and USB QR code modes using Windows 11 button states."""
        self.qr_mode = mode
        if mode == "wifi":
            self.qr_btn_wifi.configure(
                fg_color=WIN_ACCENT,
                text_color=WIN_ACCENT_TEXT,
                hover_color=WIN_ACCENT_HOVER,
                border_width=0,
                font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold")
            )
            self.qr_btn_usb.configure(
                fg_color=CONTROL_BG,
                text_color=TEXT_PRIMARY,
                hover_color=CONTROL_HOVER,
                border_width=1,
                border_color=CONTROL_BORDER,
                font=ctk.CTkFont(family="Segoe UI Variable Text", size=11)
            )
        else:
            self.qr_btn_usb.configure(
                fg_color=WIN_ACCENT,
                text_color=WIN_ACCENT_TEXT,
                hover_color=WIN_ACCENT_HOVER,
                border_width=0,
                font=ctk.CTkFont(family="Segoe UI Variable Text", size=11, weight="bold")
            )
            self.qr_btn_wifi.configure(
                fg_color=CONTROL_BG,
                text_color=TEXT_PRIMARY,
                hover_color=CONTROL_HOVER,
                border_width=1,
                border_color=CONTROL_BORDER,
                font=ctk.CTkFont(family="Segoe UI Variable Text", size=11)
            )
        self._render_current_qr()

    def _render_current_qr(self):
        """Generates and renders the QR code based on the active mode."""
        target_url = self.mobile_url if self.qr_mode == "wifi" else self.usb_url
        try:
            qr_bytes = self.server.generate_qr_code(target_url)
            pil_img = Image.open(io.BytesIO(qr_bytes)).resize((180, 180), Image.Resampling.NEAREST)
            self.qr_image_tk = ImageTk.PhotoImage(pil_img)
            self.qr_canvas.configure(image=self.qr_image_tk)
        except Exception as e:
            logger.warning(f"Failed to generate QR code: {e}")

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
        self.mobile_url = f"http://{primary_ip}:{self.port}"
        self.usb_url = f"http://localhost:{self.port}"

        self.wifi_url_lbl.configure(text=self.mobile_url)
        self.usb_url_lbl.configure(text=self.usb_url)
        self.status_dot_lbl.configure(text=f"● Active on Port {self.port}")

        self._render_current_qr()

    def start_server(self):
        if self.is_streaming:
            return

        self.port = self.server.prepare_port()
        self.broadcaster.port = self.port

        # 1. Setup WASAPI Loopback Capture
        self.audio_capture = WASAPICapture(
            sample_rate=48000,
            channels=2,
            frames_per_buffer=512,
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
        self.toggle_btn.configure(text="Stop Server", fg_color=WIN_DANGER, hover_color=WIN_DANGER_HOVER, text_color="#FFFFFF")
        self.status_pill.configure(fg_color="#102B19", border_color="#1B4A2B")
        self.status_dot_lbl.configure(text=f"● Active on Port {self.port}", text_color=WIN_SUCCESS)
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
        self.toggle_btn.configure(text="Start Server", fg_color=WIN_ACCENT, hover_color=WIN_ACCENT_HOVER, text_color=WIN_ACCENT_TEXT)
        self.status_pill.configure(fg_color="#2B2B2B", border_color="#383838")
        self.status_dot_lbl.configure(text="● Stopped", text_color=TEXT_SECONDARY)

    def toggle_server(self):
        if self.is_streaming:
            self.stop_server()
        else:
            self.start_server()

    # ── Live ADB USB Device Status Polling (every 3 seconds) ─────────────────
    def _poll_adb_status(self):
        def _check():
            try:
                adb_bin, device_id = get_adb_device()
                if adb_bin and device_id and device_id != "unauthorized":
                    setup_adb_port_forward(port=self.port)
                self.after(0, self._update_adb_badge, adb_bin, device_id)
            except Exception as e:
                logger.debug(f"ADB poll error: {e}")

        # Run in background thread so it doesn't block the GUI
        threading.Thread(target=_check, daemon=True).start()
        self.after(3000, self._poll_adb_status)

    def _update_adb_badge(self, adb_bin, device_id):
        if not adb_bin:
            self.adb_badge.configure(fg_color=CARD_BG, border_color=CARD_BORDER)
            self.adb_lbl.configure(
                text="⬤  USB (ADB): Not installed",
                text_color=TEXT_TERTIARY
            )
            self.adb_hint.configure(text="Install Android Platform Tools and add to PATH")
        elif not device_id:
            self.adb_badge.configure(fg_color=CARD_BG, border_color=CARD_BORDER)
            self.adb_lbl.configure(
                text="⬤  USB (ADB): No device",
                text_color=TEXT_TERTIARY
            )
            self.adb_hint.configure(text="Plug in phone + enable USB Debugging  →  open http://localhost on phone")
        elif device_id == "unauthorized":
            self.adb_badge.configure(fg_color="#382E14", border_color="#594619")
            self.adb_lbl.configure(
                text="⬤  USB (ADB): Unauthorized",
                text_color="#FFD60A"
            )
            self.adb_hint.configure(text="Unlock phone screen and tap 'Allow USB debugging'")
        else:
            self.adb_badge.configure(fg_color="#102B19", border_color="#1B4A2B")
            self.adb_lbl.configure(
                text=f"⬤  USB (ADB): {device_id} connected",
                text_color=WIN_SUCCESS
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

                # Wave 1 (Primary Energy: Fluent Blue)
                y1 = cy + math.sin((i / num_pts) * 4.0 * math.pi - self.wave_phase) * amp * env
                pts_main.extend([x, y1])

                # Wave 2 (Harmonic 2: Violet / Purple)
                y2 = cy + math.sin((i / num_pts) * 6.5 * math.pi + self.wave_phase * 1.4) * (amp * 0.62) * env
                pts_harm2.extend([x, y2])

                # Wave 3 (Harmonic 3: Mint / Teal)
                y3 = cy + math.sin((i / num_pts) * 9.0 * math.pi - self.wave_phase * 1.9) * (amp * 0.32) * env
                pts_harm3.extend([x, y3])

            # Draw smooth spline waves with layering
            if len(pts_main) >= 4:
                self.vu_canvas.create_line(pts_main, fill=WIN_ACCENT, width=2.0, smooth=True)
            if len(pts_harm2) >= 4:
                self.vu_canvas.create_line(pts_harm2, fill=WIN_PURPLE, width=1.5, smooth=True)
            if len(pts_harm3) >= 4:
                self.vu_canvas.create_line(pts_harm3, fill=WIN_TEAL, width=1.2, smooth=True)

        # Update Live Connection Mode Badge (USB vs Network IP)
        if self.is_streaming and self.server:
            conn_mode, conn_ip = self.server.get_connection_status()
            if conn_mode == "usb":
                self.mode_status_card.configure(fg_color="#102B19", border_color="#1B4A2B")
                self.mode_icon_lbl.configure(text="⚡ Connected: USB (Localhost)", text_color=WIN_SUCCESS)
                self.mode_detail_lbl.configure(text="ADB Reverse Tethering · Ultra-Low Latency", text_color="#A8F5B8")
            elif conn_mode == "wifi":
                self.mode_status_card.configure(fg_color="#142638", border_color="#1E4B70")
                self.mode_icon_lbl.configure(text=f"📶 Connected: Network ({conn_ip})", text_color=WIN_ACCENT)
                self.mode_detail_lbl.configure(text="Local Wi-Fi Stream · Dynamic Buffer", text_color="#B5E4FF")
            else:
                self.mode_status_card.configure(fg_color="#202020", border_color=CARD_BORDER)
                self.mode_icon_lbl.configure(text="● Waiting for Connection", text_color=TEXT_SECONDARY)
                self.mode_detail_lbl.configure(text="Scan QR or open link on phone", text_color=TEXT_SECONDARY)
        else:
            self.mode_status_card.configure(fg_color="#202020", border_color=CARD_BORDER)
            self.mode_icon_lbl.configure(text="● Server Stopped", text_color=TEXT_SECONDARY)
            self.mode_detail_lbl.configure(text="Click 'Start Server' below", text_color=TEXT_SECONDARY)

        self.after(25, self._poll_vu_meter)  # ~40 FPS smooth sinusoidal wave

    # ── Industry-Standard System Tray Lifecycle ──────────────────────────────
    def _init_tray_icon(self):
        """Creates and starts the persistent system tray icon at startup."""
        if self.tray_icon:
            return

        try:
            tray_image = generate_fluent_icon(64)

            menu = pystray.Menu(
                item('Open WinAudio Control Center', self._restore_from_tray, default=True),
                item('Copy Wi-Fi Link', self._copy_wifi_url),
                item('Copy Localhost Link', self._copy_usb_url),
                pystray.Menu.SEPARATOR,
                item('Stop / Start Server', self.toggle_server),
                pystray.Menu.SEPARATOR,
                item('Quit WinAudio', self._quit_app)
            )

            self.tray_icon = pystray.Icon("WinAudio", tray_image, "WinAudio Control Center", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            logger.warning(f"Could not initialize system tray: {e}")

    def minimize_to_tray(self):
        """Hides the window to system tray while background server keeps running."""
        self.withdraw()

    def on_close_window(self):
        """Window close ('X') handler: minimizes cleanly to tray instead of quitting."""
        self.minimize_to_tray()

    def _restore_from_tray(self, icon=None, item=None):
        """Schedules thread-safe window restoration on Tkinter main thread."""
        self.after(0, self._do_restore)

    def _do_restore(self):
        """Restores, lifts and focuses the main control center window."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self, icon=None, item=None):
        """Completely terminates system tray, audio capture, network server, and GUI."""
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
    multiprocessing.freeze_support()
    app = WinAudioGUI()
    app.mainloop()
