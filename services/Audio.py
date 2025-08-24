# -*- coding: utf-8 -*-
"""
Audio queue player for base64 audio blobs coming from Socket.IO events.
- Enqueue base64-encoded audio (mp3/wav/ogg/flac)
- Plays sequentially with a configurable gap (default 1s)
- macOS-friendly: uses the built-in `afplay` (no third-party deps)

Usage:
    from Audio import AudioQueuePlayer

    player = AudioQueuePlayer(gap_sec=1.0)

    # When you receive an event with base64 audio:
    # player.enqueue_base64(b64_string, fmt_hint="mp3")
    # ...or if the payload is a dict you can do:
    # player.enqueue_event_payload(event_dict)

    # Stop when app exits:
    # player.stop()
"""

from __future__ import annotations
import base64
import os
import platform
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import Optional, Dict, Any
import sounddevice as sd
import soundfile as sf



class AudioQueuePlayer:
    def __init__(self, gap_sec: float = 1.0):
        self.gap_sec = float(gap_sec)
        self._q: queue.Queue[tuple[str, int]] = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._current_proc: Optional[subprocess.Popen] = None
        self._tmp_files: set[str] = set()
        self._worker.start()

    # --- Public API -------------------------------------------------------
    def enqueue_base64(self, b64: str, deviceName: int, fmt_hint: Optional[str] = None) -> None:
        """Decode base64 -> temp file -> enqueue file path for playback.
        fmt_hint can be like "mp3", "wav", "audio/mpeg", etc.
        """
        print(f"456456")
        if not isinstance(b64, (bytes, str)):
            raise TypeError("b64 must be str or bytes")
        if isinstance(b64, bytes):
            b64 = b64.decode("utf-8", "ignore")

        try:
            data = base64.b64decode(b64, validate=True)
        except Exception:
            # Some backends send "data:...;base64,XXXXX"; try to split
            if "," in b64:
                data = base64.b64decode(b64.split(",", 1)[1], validate=False)
            else:
                raise
        print(f"111")
        ext = self._sniff_ext(data, fmt_hint)
        print(f"22")
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="audq_", suffix=ext)
        os.close(tmp_fd)
        with open(tmp_path, "wb") as f:
            f.write(data)
        print(f"33")
        self._tmp_files.add(tmp_path)
        print("deviceid. :",deviceName)
        self._q.put((tmp_path, deviceName))

    def enqueue_event_payload(self, payload: Dict[str, Any], deviceName: str) -> None:
        """Convenience: try common keys in your event payload.
        Example payloads:
          {"audio": "<base64>", "format": "mp3"}
          {"data": {"base64": "...", "mime": "audio/mpeg"}}
        """
        # Try a few common shapes
        cand = None
        hint = None
        if isinstance(payload, dict):
            if "audio" in payload and isinstance(payload["audio"], (str, bytes)):
                cand = payload["audio"]
                hint = payload.get("format") or payload.get("mime")
            elif "data" in payload and isinstance(payload["data"], dict):
                d = payload["data"]
                cand = d.get("audio") or d.get("base64") or d.get("blob")
                hint = d.get("format") or d.get("mime")
        if cand is None:
            raise ValueError("payload does not contain a base64 audio field")
        self.enqueue_base64(cand, hint, deviceName)

    def stop(self) -> None:
        """Stop the background worker and cleanup temp files."""
        self._stop.set()
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.send_signal(signal.SIGTERM)
            except Exception:
                pass
        self._worker.join(timeout=5)
        # cleanup tmp files
        for p in list(self._tmp_files):
            try:
                os.remove(p)
            except Exception:
                pass
            finally:
                self._tmp_files.discard(p)

    # --- Internals --------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                path, deviceName = self._q.get(timeout=0.25)
                print("deviceID:",deviceName)
            except queue.Empty:
                continue
            try:
                self._play_file(path, deviceName)
            finally:
                # remove after play to avoid disk pile-up
                try:
                    os.remove(path)
                except Exception:
                    pass
                self._tmp_files.discard(path)
                self._q.task_done()
                # inter-item gap
                self._sleep_interruptible(self.gap_sec)

    def _find_ffplay(self) -> Optional[str]:
        # Prefer a bundled ffplay.exe next to this file; fallback to PATH
        candidates = []
        base = os.path.abspath(os.path.dirname(__file__))
        candidates.append(os.path.join(base, 'ffplay.exe'))
        # On mac/linux also allow plain 'ffplay'
        candidates.append(shutil.which('ffplay'))
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def _play_file(self, path: str, deviceName) -> None:
        # Use sounddevice to play audio on specified device
        system = platform.system()
        try:
            import soundfile as sf
            for i, d in enumerate(sd.query_devices()):
                print(f"[{i}] {d['name']} | hostapi: {d['hostapi']} | max_output_channels: {d['max_output_channels']}")
            data, samplerate = sf.read(path, dtype='float32')
            print("device id:", deviceName)
            sd.play(data, samplerate=samplerate, device=deviceName)
            sd.wait()
        except Exception as e:
            print(f"[warn] sounddevice playback failed: {e}")

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep in small slices so `stop()` can interrupt promptly."""
        end = time.time() + float(seconds)
        while not self._stop.is_set():
            remaining = end - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))

    @staticmethod
    def _sniff_ext(data: bytes, hint: Optional[str]) -> str:
        h = (hint or "").lower()
        if h in ("mp3", "audio/mpeg", "mpeg", "mpga"):  # mp3
            return ".mp3"
        if h in ("wav", "audio/wav", "audio/x-wav"):
            return ".wav"
        if h in ("flac", "audio/flac"):
            return ".flac"
        if h in ("ogg", "audio/ogg"):
            return ".ogg"
        # Magic sniff
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            return ".wav"
        if data[:3] == b"ID3" or (len(data) > 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
            return ".mp3"
        if data[:4] == b"fLaC":
            return ".flac"
        if data[:4] == b"OggS":
            return ".ogg"
        # default
        return ".mp3"


# Convenience singleton (optional):
_default_player: Optional[AudioQueuePlayer] = None

def get_player(gap_sec: float = 1.0) -> AudioQueuePlayer:
    global _default_player
    if _default_player is None:
        _default_player = AudioQueuePlayer(gap_sec=gap_sec)
    return _default_player