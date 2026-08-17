import asyncio
import fractions
import time
import logging
import numpy as np
import av
from aiortc import MediaStreamTrack

logger = logging.getLogger("WinAudio.WebRTC")

class WinAudioTrack(MediaStreamTrack):
    """
    Ultra-Low Latency WebRTC Audio Stream Track capturing WASAPI Loopback PCM
    and encoding it into 48kHz Studio-Quality Stereo Opus (10ms frames) over UDP.
    """
    kind = "audio"

    def __init__(self, sample_rate=48000, channels=2):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        # 10ms at 48kHz = 480 samples (half the latency of standard 20ms frames)
        self.frame_samples = 480
        
        self.queue = asyncio.Queue(maxsize=30)
        self._timestamp = 0
        self._buffer = bytearray()
        self._bytes_per_sample = 2 * channels  # 4 bytes for 16-bit stereo
        self._bytes_needed = self.frame_samples * self._bytes_per_sample

    def push_pcm(self, pcm_bytes: bytes):
        """Pushes raw int16 stereo PCM bytes from WASAPI capture into WebRTC queue."""
        if self.queue.full():
            try:
                self.queue.get_nowait()  # Drop oldest frame to ensure zero lag
            except asyncio.QueueEmpty:
                pass
        try:
            self.queue.put_nowait(pcm_bytes)
        except asyncio.QueueFull:
            pass

    async def recv(self):
        """
        Called by aiortc for each audio frame. Assembles 10ms (480 samples)
        and returns an av.AudioFrame ready for high-fidelity Opus encoding.
        """
        # Assemble 10ms of audio (480 samples * 4 bytes = 1920 bytes)
        while len(self._buffer) < self._bytes_needed:
            try:
                chunk = await asyncio.wait_for(self.queue.get(), timeout=0.015)
                self._buffer.extend(chunk)
            except asyncio.TimeoutError:
                # Silence padding if stream temporarily pauses
                break

        if len(self._buffer) >= self._bytes_needed:
            raw_bytes = bytes(self._buffer[:self._bytes_needed])
            del self._buffer[:self._bytes_needed]
            arr = np.frombuffer(raw_bytes, dtype=np.int16).reshape(1, -1)
        else:
            # Silence padding (1, samples * channels)
            arr = np.zeros((1, self.frame_samples * self.channels), dtype=np.int16)

        frame = av.AudioFrame.from_ndarray(arr, format='s16', layout='stereo')
        frame.sample_rate = self.sample_rate
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        
        self._timestamp += self.frame_samples
        return frame
