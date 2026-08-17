import sys
import time
import ctypes
import threading
import logging
import numpy as np
import pyaudiowpatch as pyaudio

logger = logging.getLogger("WinAudio.Capture")

# Set MMCSS thread priority for Windows Pro Audio latency
def set_thread_mmcss_priority():
    if sys.platform == "win32":
        try:
            avrt = ctypes.windll.avrt
            task_name = ctypes.c_wchar_p("Pro Audio")
            task_index = ctypes.c_ulong(0)
            handle = avrt.AvSetMmThreadCharacteristicsW(task_name, ctypes.byref(task_index))
            if handle:
                logger.info("Elevated thread MMCSS priority to 'Pro Audio'")
                return handle
        except Exception as e:
            logger.warning(f"Could not set MMCSS thread priority: {e}")
    return None

class WASAPICapture:
    """
    Captures Windows system audio output via WASAPI Loopback with ultra-low latency.
    """
    def __init__(self, sample_rate=48000, channels=2, frames_per_buffer=256, on_audio_chunk=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames_per_buffer = frames_per_buffer  # 256 samples = ~5.3ms buffer at 48kHz
        self.on_audio_chunk = on_audio_chunk


        self.pyaudio_instance = None
        self.stream = None
        self.is_running = False
        self.thread = None

        self.device_name = "Unknown"
        self.actual_sample_rate = sample_rate
        self.actual_channels = channels

        # Audio visualizer metric
        self.current_peak = 0.0

    def get_loopback_device(self, p):
        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError as e:
            raise RuntimeError("WASAPI Host API not found on this Windows system!") from e

        default_speakers = p.get_device_info_by_index(wasapi_info['defaultOutputDevice'])
        logger.info(f"Default Playback Device: {default_speakers['name']}")

        # Look for matching WASAPI loopback device
        loopback_device = None
        if default_speakers.get('isLoopbackDevice', False):
            loopback_device = default_speakers
        else:
            for dev in p.get_loopback_device_info_generator():
                if default_speakers['name'] in dev['name']:
                    loopback_device = dev
                    break
        
        if not loopback_device:
            # Fallback to first available loopback device
            loopback_devices = list(p.get_loopback_device_info_generator())
            if loopback_devices:
                loopback_device = loopback_devices[0]
            else:
                raise RuntimeError("No WASAPI Loopback device found.")

        return loopback_device

    def start(self):
        if self.is_running:
            return

        self.pyaudio_instance = pyaudio.PyAudio()
        loopback_dev = self.get_loopback_device(self.pyaudio_instance)

        self.device_name = loopback_dev['name']
        self.actual_sample_rate = int(loopback_dev['defaultSampleRate'])
        self.actual_channels = int(loopback_dev['maxInputChannels'])

        logger.info(f"Opening WASAPI Loopback: {self.device_name}")
        logger.info(f"Audio Format: {self.actual_sample_rate} Hz, {self.actual_channels} Channels, Buffer: {self.frames_per_buffer} frames")

        def audio_callback(in_data, frame_count, time_info, status):
            if in_data:
                # Convert raw byte data to int16 PCM numpy array for fast peak measurement & processing
                try:
                    # Input is float32 or int16 depending on WASAPI driver
                    # WASAPI Loopback in pyaudiowpatch delivers float32 PCM by default
                    samples = np.frombuffer(in_data, dtype=np.float32)
                    
                    if len(samples) > 0:
                        # Calculate peak volume metric for GUI visualizer
                        peak = np.abs(samples).max()
                        self.current_peak = float(peak)

                        # Convert float32 [-1.0, 1.0] to int16 [-32768, 32767] for network transport
                        int16_samples = (samples * 32767.0).clip(-32768, 32767).astype(np.int16)
                        pcm_bytes = int16_samples.tobytes()

                        if self.on_audio_chunk:
                            self.on_audio_chunk(pcm_bytes, self.actual_sample_rate, self.actual_channels)
                except Exception as e:
                    logger.error(f"Error processing audio frame callback: {e}")

            return (None, pyaudio.paContinue)

        # Set MMCSS priority before opening stream
        mmcss_handle = set_thread_mmcss_priority()

        try:
            self.stream = self.pyaudio_instance.open(
                format=pyaudio.paFloat32,
                channels=self.actual_channels,
                rate=self.actual_sample_rate,
                input=True,
                input_device_index=loopback_dev['index'],
                frames_per_buffer=self.frames_per_buffer,
                stream_callback=audio_callback
            )
            self.is_running = True
            self.stream.start_stream()
            logger.info("WASAPI Loopback Capture active and streaming.")
        except Exception as e:
            self.is_running = False
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
            raise RuntimeError(f"Failed to start WASAPI Loopback stream: {e}") from e

    def stop(self):
        self.is_running = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception:
                pass
            self.pyaudio_instance = None
        logger.info("WASAPI Loopback Capture stopped.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing WASAPICapture module...")
    captured_bytes = 0
    def print_chunk(data, rate, channels):
        global captured_bytes
        captured_bytes += len(data)

    cap = WASAPICapture(on_audio_chunk=print_chunk)
    cap.start()
    time.sleep(2)
    print(f"Captured {captured_bytes} bytes in 2 seconds.")
    cap.stop()
