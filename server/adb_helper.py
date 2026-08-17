import os
import shutil
import socket
import subprocess
import logging

logger = logging.getLogger("WinAudio.ADB")

def find_adb_path():
    """Look for adb in PATH, common Android SDK locations, or local directory."""
    adb_cmd = shutil.which("adb")
    if adb_cmd:
        return adb_cmd

    # Check common Windows locations
    user_home = os.path.expanduser("~")
    common_paths = [
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
        res = subprocess.run([adb_bin, "devices"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                return adb_bin, parts[0]
    except Exception:
        pass
    return None, None

def setup_adb_port_forward(port=8080):
    """
    Sets up ADB REVERSE port forwarding:
      adb reverse tcp:<port> tcp:<port>

    This allows the phone to open http://localhost:<port> and have it
    tunneled through the USB cable to the PC server on that port.
    Returns (success, message).
    """
    adb_bin, device_id = get_adb_device()

    if not adb_bin:
        logger.info("ADB executable not found in PATH or standard SDK paths.")
        return False, "ADB not found"

    if not device_id:
        logger.info("ADB found, but no USB device attached with USB Debugging enabled.")
        return False, "No USB device connected"

    try:
        # adb reverse makes phone's localhost:<port> → PC's localhost:<port>
        rev_res = subprocess.run(
            [adb_bin, "reverse", f"tcp:{port}", f"tcp:{port}"],
            capture_output=True, text=True, timeout=5
        )
        if rev_res.returncode == 0:
            logger.info(f"ADB reverse tunnel active: phone localhost:{port} → PC:{port} (device: {device_id})")
            return True, device_id
        else:
            err = rev_res.stderr.strip() or rev_res.stdout.strip()
            logger.warning(f"ADB reverse failed: {err}")
            return False, f"ADB reverse error: {err}"
    except Exception as e:
        logger.warning(f"Error running ADB reverse: {e}")
        return False, str(e)

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
