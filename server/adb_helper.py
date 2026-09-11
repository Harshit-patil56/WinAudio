import os
import sys
import shutil
import socket
import subprocess
import logging

logger = logging.getLogger("WinAudio.ADB")

# ── Windows: suppress console window for every adb.exe call ──────────────────
# When WinAudio.exe is compiled with --noconsole (GUI subsystem), calling any
# console application (adb.exe) WITHOUT this flag causes Windows to allocate
# and briefly show a black console window for each subprocess — that is the
# "open and close" flash the user sees. CREATE_NO_WINDOW (0x08000000) is the
# Win32 process creation flag that prevents this. capture_output=True only
# redirects streams; it does NOT suppress the window. These are separate.
_WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def _run_adb(args, timeout=5):
    """
    Run an adb command suppressing any console window on Windows.
    Returns CompletedProcess or raises on timeout/error.
    """
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_WIN_NO_WINDOW
    )

def find_adb_path():
    """Look for bundled adb first, then executable directory, project root, and finally PATH / SDK."""
    # 1. PyInstaller bundled temp extraction dir (_MEIPASS)
    if hasattr(sys, '_MEIPASS'):
        for sub in ["platform-tools", ""]:
            cand = os.path.join(sys._MEIPASS, sub, "adb.exe") if sub else os.path.join(sys._MEIPASS, "adb.exe")
            if os.path.exists(cand):
                return cand

    # 2. Directory containing executable or script, and project root
    search_dirs = []
    if getattr(sys, 'frozen', False):
        search_dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    this_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs.append(this_dir)
    search_dirs.append(os.path.dirname(this_dir))  # Project root
    search_dirs.append(os.getcwd())

    for d in search_dirs:
        for sub in ["platform-tools", "bin", ""]:
            cand = os.path.join(d, sub, "adb.exe") if sub else os.path.join(d, "adb.exe")
            if os.path.exists(cand):
                return cand

    # 3. System PATH
    adb_cmd = shutil.which("adb")
    if adb_cmd:
        return adb_cmd

    # 4. Common Windows SDK locations
    user_home = os.path.expanduser("~")
    common_paths = [
        os.path.join(user_home, "Downloads", "platform-tools-latest-windows", "platform-tools", "adb.exe"),
        os.path.join(user_home, "Downloads", "platform-tools", "adb.exe"),
        os.path.join(user_home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
        r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
        r"C:\Android\platform-tools\adb.exe",
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return None

def get_adb_device():
    """
    Returns (adb_bin, device_id) if a USB-debuggable device is connected, else (None, None).
    Does NOT run forward/reverse — just detects.
    """
    adb_bin = find_adb_path()
    if not adb_bin:
        return None, None
    try:
        res = _run_adb([adb_bin, "devices"])
        for line in res.stdout.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2:
                if parts[1] == "device":
                    return adb_bin, parts[0]
                elif parts[1] == "unauthorized":
                    return adb_bin, "unauthorized"
    except Exception:
        pass
    return adb_bin, None

_cached_adb_device = (None, None)
_last_adb_check = 0

def get_cached_adb_device(cache_ttl=2.0):
    """
    Returns (adb_bin, device_id) with short TTL caching to prevent
    repeated subprocess spawning on frequent status checks.
    """
    import time
    global _cached_adb_device, _last_adb_check
    now = time.time()
    if now - _last_adb_check > cache_ttl:
        _cached_adb_device = get_adb_device()
        _last_adb_check = now
    return _cached_adb_device

# Module-level set tracking ports whose ADB reverse tunnel is confirmed active.
# Key: (device_id, port). Cleared when device changes or tunnel teardown is detected.
_active_reverse_tunnels: set = set()

def is_reverse_already_active(adb_bin: str, device_id: str, port: int) -> bool:
    """
    Checks 'adb reverse --list' to see if tcp:<port> is already forwarded.
    Returns True if the tunnel is already set up — no need to call adb reverse again.
    """
    # Fast path: we already tracked this tunnel in-process
    if (device_id, port) in _active_reverse_tunnels:
        return True
    # Slow path: ask ADB (only runs once per device+port until we confirm it's gone)
    try:
        res = _run_adb([adb_bin, "reverse", "--list"])
        for line in res.stdout.splitlines():
            # Output format: "(reverse) tcp:<port>  tcp:<port>"
            if f"tcp:{port}" in line:
                _active_reverse_tunnels.add((device_id, port))
                return True
    except Exception:
        pass
    return False

def setup_adb_port_forward(port=8080, adb_bin=None, device_id=None):
    """
    Sets up ADB REVERSE port forwarding:
      adb reverse tcp:<port> tcp:<port>

    This allows the phone to open http://localhost:<port> and have it
    tunneled through the USB cable to the PC server on that port.

    Pass pre-fetched adb_bin / device_id to avoid a redundant subprocess
    call when the caller has already run get_adb_device().

    Returns (success, message).
    """
    global _active_reverse_tunnels

    # Use pre-fetched values if provided, otherwise look them up once.
    if adb_bin is None or device_id is None:
        adb_bin, device_id = get_cached_adb_device(cache_ttl=3.0)

    if not adb_bin:
        logger.info("ADB executable not found in PATH or standard SDK paths.")
        return False, "ADB not found"

    if not device_id or device_id == "unauthorized":
        logger.info("ADB found, but no USB device attached with USB Debugging enabled.")
        # If device disappeared, clear our tunnel tracking for this port.
        _active_reverse_tunnels.discard((device_id, port))
        return False, "No USB device connected"

    # ── GUARDRAIL: skip if the tunnel is already active ──────────────────────
    if is_reverse_already_active(adb_bin, device_id, port):
        logger.debug(f"ADB reverse tcp:{port} already active for {device_id} — skipping.")
        return True, device_id

    try:
        # adb reverse makes phone's localhost:<port> → PC's localhost:<port>
        rev_res = _run_adb([adb_bin, "reverse", f"tcp:{port}", f"tcp:{port}"])
        if rev_res.returncode == 0:
            _active_reverse_tunnels.add((device_id, port))
            logger.info(f"ADB reverse tunnel set up: phone localhost:{port} → PC:{port} (device: {device_id})")
            return True, device_id
        else:
            err = rev_res.stderr.strip() or rev_res.stdout.strip()
            logger.warning(f"ADB reverse failed: {err}")
            return False, f"ADB reverse error: {err}"
    except Exception as e:
        logger.warning(f"Error running ADB reverse: {e}")
        return False, str(e)

def teardown_adb_port_forward(port=8080):
    """
    Removes the ADB reverse tunnel for the given port and clears our tracking.
    Called when the server stops so the next start will re-establish cleanly.
    """
    global _active_reverse_tunnels
    adb_bin, device_id = get_cached_adb_device(cache_ttl=3.0)
    if adb_bin and device_id and device_id != "unauthorized":
        try:
            _run_adb([adb_bin, "reverse", "--remove", f"tcp:{port}"])
        except Exception:
            pass
    # Clear all tracked tunnels for this port regardless
    _active_reverse_tunnels = {t for t in _active_reverse_tunnels if t[1] != port}

def get_network_ip_addresses():
    """
    Returns list of local IP addresses (Ethernet, Wi-Fi, USB Tethering).
    Uses ifaddr to discover all network adapters including Samsung/Android/iPhone USB RNDIS.
    """
    ip_list = []
    seen = set()

    try:
        import ifaddr
        adapters = ifaddr.get_adapters()
        for adapter in adapters:
            name_lower = adapter.nice_name.lower()
            # Detect USB NDIS / tethering indicators
            is_usb = any(k in name_lower for k in [
                "usb", "ndis", "rndis", "tethering", "remote ndis", "samsung", "apple", "mobile"
            ])
            
            for ip in adapter.ips:
                if isinstance(ip.ip, str) and not ip.ip.startswith("127.") and not ip.ip.startswith("169.254"):
                    if ip.ip not in seen:
                        seen.add(ip.ip)
                        # Check USB IP ranges
                        if any(ip.ip.startswith(prefix) for prefix in ["192.168.42.", "192.168.49.", "172.20.", "10.23."]):
                            is_usb = True

                        ip_list.append({
                            "ip": ip.ip,
                            "type": f"USB Cable ({adapter.nice_name})" if is_usb else f"Wi-Fi / LAN ({adapter.nice_name})"
                        })
    except Exception as e:
        logger.error(f"Error enumerating IP addresses with ifaddr: {e}")

    # Fallback if no list found
    if not ip_list:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and ip != "127.0.0.1":
                ip_list.append({"ip": ip, "type": "LAN"})
        except Exception:
            pass

    return ip_list


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Network IP Addresses:")
    for net in get_network_ip_addresses():
        print(f" - {net['ip']} ({net['type']})")
    
    status, msg = setup_adb_port_forward()
    print(f"ADB USB Port Forward Status: {status} -> {msg}")
