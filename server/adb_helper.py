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

def setup_adb_port_forward(port=8080):
    """
    Sets up ADB port forwarding (adb forward tcp:PORT tcp:PORT) for zero-latency USB connection.
    Returns (success, message_or_device_id).
    """
    adb_bin = find_adb_path()
    if not adb_bin:
        logger.info("ADB executable not found in PATH or standard SDK paths.")
        return False, "ADB not found"

    try:
        # Check connected devices
        res = subprocess.run([adb_bin, "devices"], capture_output=True, text=True, timeout=5)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        
        devices = []
        for line in lines[1:]: # Skip 'List of devices attached'
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])

        if not devices:
            logger.info("ADB found, but no USB devices attached in debugging mode.")
            return False, "No USB devices connected via ADB"

        device_id = devices[0]
        # Execute port forward
        fwd_res = subprocess.run([adb_bin, "forward", f"tcp:{port}", f"tcp:{port}"], capture_output=True, text=True, timeout=5)
        if fwd_res.returncode == 0:
            logger.info(f"Successfully configured ADB USB port forward tcp:{port} for device {device_id}")
            return True, f"ADB USB connected ({device_id})"
        else:
            return False, f"ADB forward error: {fwd_res.stderr.strip()}"
    except Exception as e:
        logger.warning(f"Error executing ADB setup: {e}")
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
