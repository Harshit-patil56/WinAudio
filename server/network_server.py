import os
import io
import asyncio
import logging
import socket
import qrcode
from aiohttp import web, WSMsgType
from aiortc import RTCPeerConnection, RTCSessionDescription
from .webrtc_track import WinAudioTrack
from .adb_helper import get_cached_adb_device

logger = logging.getLogger("WinAudio.Server")

def find_available_port(host="0.0.0.0", start_port=8080, max_attempts=20):
    """Finds an available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start_port

class ClientHandler:
    """Thread-safe single-sender queue handler for WebSocket clients."""
    def __init__(self, ws_response, loop):
        self.ws = ws_response
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=16)
        self.send_task = None

    def start(self):
        self.send_task = asyncio.create_task(self._send_loop())

    def stop(self):
        if self.send_task:
            self.send_task.cancel()

    def push(self, data):
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    async def _send_loop(self):
        try:
            while True:
                data = await self.queue.get()
                await self.ws.send_bytes(data)
                self.queue.task_done()
        except (asyncio.CancelledError, Exception):
            pass

class WinAudioNetworkServer:
    """
    High-Performance WebRTC (UDP + Opus 48kHz) & WebSocket Dual Audio Streaming Server.
    """
    def __init__(self, host="0.0.0.0", port=8080, web_dir="web"):
        self.host = host
        self.port = port
        self.web_dir = os.path.abspath(web_dir)
        self.app = None   # Created lazily inside run_server() in the correct event loop
        self.runner = None
        self.site = None
        self.loop = None

        # Connected client registries
        self.clients = {}      # ws_response -> ClientHandler
        self.client_ips = {}   # ws_response -> remote_ip string
        self.client_modes = {} # ws_response -> 'usb' | 'wifi' (client-reported)
        self.pcs = set()       # RTCPeerConnection instances
        self.webrtc_tracks = set()  # WinAudioTrack instances

    def prepare_port(self):
        actual_port = find_available_port(self.host, self.port)
        if actual_port != self.port:
            logger.info(f"Port {self.port} is busy. Automatically switched to port {actual_port}.")
            self.port = actual_port
        return self.port

    def generate_qr_code(self, target_url):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=2,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def generate_ascii_qr(self, target_url):
        qr = qrcode.QRCode(border=1)
        qr.add_data(target_url)
        qr.make(fit=True)
        f = io.StringIO()
        qr.print_ascii(out=f)
        return f.getvalue()

    def _setup_routes(self):
        """Register URL routes on self.app. Must be called after self.app is created."""
        self.app.router.add_get('/', self._handle_index)
        self.app.router.add_get('/ws', self._handle_ws)
        self.app.router.add_get('/api/usb-status', self._handle_usb_status)
        self.app.router.add_post('/offer', self._handle_offer)
        self.app.router.add_static('/', self.web_dir, show_index=True)

    @web.middleware
    async def _security_headers_middleware(self, request, handler):
        response = await handler(request)
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        return response

    async def _handle_index(self, request):
        index_file = os.path.join(self.web_dir, "index.html")
        return web.FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache",
                "Cross-Origin-Opener-Policy": "same-origin",
                "Cross-Origin-Embedder-Policy": "require-corp",
                "Cross-Origin-Resource-Policy": "same-origin"
            }
        )

    async def _handle_usb_status(self, request):
        """Returns JSON status indicating whether a real USB connection is active."""
        client_ip = request.remote or ""
        is_local = client_ip in ("127.0.0.1", "::1", "localhost")
        adb_bin, device_id = get_cached_adb_device()
        # USB is only valid if request is routed via loopback (ADB reverse) AND a USB device is attached
        usb_connected = bool(is_local and device_id)
        return web.json_response({
            "usb_connected": usb_connected,
            "device_id": device_id,
            "client_ip": client_ip,
            "is_local": is_local,
            "adb_available": bool(adb_bin)
        }, headers={"Cache-Control": "no-cache"})

    def get_connection_status(self):
        """Returns tuple (mode, remote_ip) where mode is 'usb', 'wifi', or 'none'.
        Strictly enforces that USB mode is only reported when client is local AND USB device is connected."""
        if not self.clients:
            return "none", None
        for ws, mode in list(self.client_modes.items()):
            remote = self.client_ips.get(ws, "connected")
            if mode == 'usb':
                is_local = remote in ('127.0.0.1', '::1', 'localhost')
                adb_bin, device_id = get_cached_adb_device()
                if not is_local or not device_id:
                    return "wifi", remote
            return mode, remote
        return "wifi", "connected"

    async def _handle_ws(self, request):
        ws = web.WebSocketResponse(heartbeat=15.0)
        await ws.prepare(request)

        client_ip = request.remote or "unknown"
        is_local = client_ip in ("127.0.0.1", "::1", "localhost")
        try:
            transport = request.transport
            if transport:
                sock = transport.get_extra_info('socket')
                if sock:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

        handler = ClientHandler(ws, self.loop)
        handler.start()
        self.clients[ws] = handler
        self.client_ips[ws] = client_ip
        # Mode defaults to wifi until client sends its verified mode message
        self.client_modes[ws] = "wifi"
        logger.info(f"WebSocket client connected from {client_ip} (Total: {len(self.clients)})")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = msg.data
                    if data == 'ping':
                        await ws.send_str('pong')
                    else:
                        # Try to parse JSON mode report from browser
                        try:
                            import json as _json
                            parsed = _json.loads(data)
                            if parsed.get('type') == 'mode':
                                reported = parsed.get('mode', 'wifi')
                                if reported == 'usb':
                                    adb_bin, device_id = get_cached_adb_device()
                                    if not is_local:
                                        logger.warning(f"Rejecting USB mode from non-local client {client_ip} (Wi-Fi)")
                                        reported = 'wifi'
                                        try:
                                            await ws.send_str(_json.dumps({
                                                "type": "error",
                                                "message": "USB mode cannot be used over Wi-Fi."
                                            }))
                                        except Exception:
                                            pass
                                    elif not device_id:
                                        logger.warning(f"Rejecting USB mode from local client {client_ip}: No USB device connected")
                                        reported = 'wifi'
                                        try:
                                            await ws.send_str(_json.dumps({
                                                "type": "error",
                                                "message": "No USB device connected."
                                            }))
                                        except Exception:
                                            pass
                                self.client_modes[ws] = reported
                                logger.info(f"Client connection mode set to: {reported} (from {client_ip})")
                        except Exception:
                            pass
                elif msg.type == WSMsgType.ERROR:
                    logger.debug(f"WS error: {ws.exception()}")
        finally:
            handler.stop()
            if ws in self.clients:
                del self.clients[ws]
            if ws in self.client_ips:
                del self.client_ips[ws]
            if ws in self.client_modes:
                del self.client_modes[ws]
            logger.info("WebSocket audio client disconnected")

        return ws

    async def _handle_offer(self, request):
        """WebRTC SDP Offer / Answer Signaling Handler."""
        try:
            params = await request.json()
            offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

            pc = RTCPeerConnection()
            self.pcs.add(pc)

            track = WinAudioTrack(sample_rate=48000, channels=2)
            self.webrtc_tracks.add(track)
            pc.addTrack(track)

            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(f"WebRTC Connection State: {pc.connectionState}")
                if pc.connectionState in ["failed", "closed"]:
                    await pc.close()
                    self.pcs.discard(pc)
                    self.webrtc_tracks.discard(track)

            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()

            # Inject studio-grade Opus parameters: 256kbps, Full Stereo, 10ms ptime, FEC & CBR
            sdp_str = answer.sdp
            if "useinbandfec=1" in sdp_str:
                sdp_str = sdp_str.replace(
                    "useinbandfec=1",
                    "useinbandfec=1;stereo=1;sprop-stereo=1;maxaveragebitrate=256000;minptime=10;cbr=1"
                )
            elif "opus/48000/2" in sdp_str:
                sdp_str = sdp_str.replace(
                    "a=rtpmap:111 opus/48000/2",
                    "a=rtpmap:111 opus/48000/2\r\na=fmtp:111 minptime=10;useinbandfec=1;stereo=1;sprop-stereo=1;maxaveragebitrate=256000;cbr=1"
                )

            answer = RTCSessionDescription(sdp=sdp_str, type=answer.type)
            await pc.setLocalDescription(answer)

            logger.info("WebRTC PeerConnection established (UDP + Opus 48kHz 256kbps Studio Stereo)")
            return web.json_response({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }, headers={
                "Cache-Control": "no-cache"
            })
        except Exception as e:
            logger.error(f"Error handling WebRTC offer: {e}")
            return web.json_response({"error": str(e)}, status=500)

    def broadcast_pcm(self, pcm_bytes):
        """Broadcasts PCM audio chunks to all active WebRTC Opus tracks and WebSocket clients."""
        if not self.loop:
            return

        # 1. Feed WebRTC Opus Tracks (Ultra-Low Latency UDP)
        if self.webrtc_tracks:
            for track in list(self.webrtc_tracks):
                try:
                    track.push_pcm(pcm_bytes)
                except Exception:
                    pass

        # 2. Feed WebSocket Clients (TCP Fallback)
        if self.clients:
            for handler in list(self.clients.values()):
                try:
                    self.loop.call_soon_threadsafe(handler.push, pcm_bytes)
                except Exception:
                    pass

    async def run_server(self):
        # Create web.Application HERE so it belongs to this event loop (fixes aiohttp loop mismatch)
        self.app = web.Application()
        self._setup_routes()

        self.loop = asyncio.get_running_loop()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        logger.info(f"WinAudio WebRTC & HTTP Server active on http://{self.host}:{self.port}")

        # Keep server running indefinitely
        while True:
            await asyncio.sleep(3600)

    async def cleanup(self):
        # Close all active WebRTC peer connections
        coros = [pc.close() for pc in self.pcs]
        await asyncio.gather(*coros, return_exceptions=True)
        self.pcs.clear()
        self.webrtc_tracks.clear()

        # Close all WebSocket clients
        for ws in list(self.clients.keys()):
            await ws.close()
        self.clients.clear()

        if self.runner:
            await self.runner.cleanup()
