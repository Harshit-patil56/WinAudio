import socket
import logging
import ifaddr

logger = logging.getLogger("WinAudio.Zeroconf")

def _get_primary_ip():
    """
    Returns the best local IP for mDNS: prefer Wi-Fi/Ethernet,
    never USB RNDIS adapters (10.23.x.x range) which can vanish at runtime.
    Falls back to hostname resolution if nothing better is found.
    """
    RNDIS_PREFIXES = ("10.23.", "192.168.42.", "192.168.49.")

    candidates = []
    try:
        adapters = ifaddr.get_adapters()
        for adapter in adapters:
            for ip in adapter.ips:
                if not isinstance(ip.ip, str):
                    continue
                addr = ip.ip
                if addr.startswith("127.") or addr.startswith("169.254."):
                    continue
                # Skip USB RNDIS — they disappear when cable disconnects
                if any(addr.startswith(p) for p in RNDIS_PREFIXES):
                    continue
                # Prefer 192.168.x.x (typical Wi-Fi/LAN)
                priority = 0 if addr.startswith("192.168.") else 1
                candidates.append((priority, addr))
    except Exception:
        pass

    if candidates:
        candidates.sort()
        return candidates[0][1]

    # Last-resort fallback
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


class WinAudioBroadcaster:
    """
    Broadcasts WinAudio PC Server on local network via mDNS Zeroconf.
    Only binds to stable interfaces (Wi-Fi/Ethernet) — never USB RNDIS.
    """
    def __init__(self, port=8080, name="WinAudio-PC"):
        self.port = port
        self.name = name
        self.zeroconf = None
        self.service_info = None

    def start(self):
        try:
            from zeroconf import Zeroconf, ServiceInfo

            local_ip = _get_primary_ip()
            hostname = socket.gethostname()

            self.service_info = ServiceInfo(
                "_winaudio._tcp.local.",
                f"{self.name}._winaudio._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={"version": "1.0.0", "path": "/"},
                server=f"{hostname}.local.",
            )

            # Bind Zeroconf only to the chosen stable interface IP.
            # This prevents OSError/WinError 59 from unstable USB RNDIS interfaces.
            self.zeroconf = Zeroconf(interfaces=[local_ip])
            self.zeroconf.register_service(self.service_info)
            logger.info(f"mDNS Zeroconf broadcasting '{self.name}' on {local_ip}:{self.port}")
        except Exception as e:
            logger.warning(f"Could not start Zeroconf service: {e}")
            self.zeroconf = None
            self.service_info = None

    def stop(self):
        if self.zeroconf and self.service_info:
            try:
                self.zeroconf.unregister_service(self.service_info)
            except Exception:
                pass
            try:
                self.zeroconf.close()
            except Exception:
                pass
            logger.info("Zeroconf service stopped.")
        self.zeroconf = None
        self.service_info = None
