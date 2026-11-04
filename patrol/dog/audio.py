"""Dog speaker + microphone helpers (no vendor library, no network).

Speaker
- `SpeakerTrack` is an aiortc audio track. RealDog puts it on the audio transceiver
  that unitree_webrtc_connect already creates ("sendrecv"), with `sender.replaceTrack`,
  so no renegotiation is needed.
- It sends 20 ms frames of 48 kHz mono s16 in real time: queued PCM when there is
  some, silence otherwise. RTP timestamps therefore stay continuous.
- Nothing is uploaded or stored on the dog. We deliberately do NOT use the vendor's
  audiohub upload API (it writes files onto the dog).

Microphone
- `MicTap.feed()` takes the dog's received audio frames (aiortc AudioFrame, normally
  48 kHz stereo s16), converts them to mono s16 48 kHz, keeps a level meter and fans
  the PCM out to subscriber queues at any sample rate (WAV recorder, browser
  "listen", a speech-to-text client).

All PCM in this module is little-endian signed 16-bit ("s16").
"""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import subprocess
import tempfile
import time
import wave
from collections import deque
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError

RATE = 48000                 # WebRTC / Opus rate
FRAME_SAMPLES = 960          # 20 ms
FRAME_S = FRAME_SAMPLES / RATE
MAX_BUFFER_S = 300.0         # speaker queue cap (5 min)
LEVEL_WINDOW_S = 0.3         # level meters report the peak over this window
SILENCE_DBFS = -90.0
MAX_SAY_CHARS = 400


def _dbfs(a: np.ndarray) -> float:
    if a.size == 0:
        return SILENCE_DBFS
    rms = float(np.sqrt(np.mean(np.square(a.astype(np.float64)))))
    if rms < 1.0:
        return SILENCE_DBFS
    return round(max(SILENCE_DBFS, 20.0 * math.log10(rms / 32768.0)), 1)


class _Level:
    """Peak-hold of per-frame RMS dBFS over a short window."""

    def __init__(self) -> None:
        self._v: deque[tuple[float, float]] = deque()

    def add(self, db: float, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._v.append((now, db))
        while self._v and now - self._v[0][0] > LEVEL_WINDOW_S:
            self._v.popleft()

    def value(self, now: float | None = None) -> float | None:
        now = time.monotonic() if now is None else now
        vals = [d for t, d in self._v if now - t <= LEVEL_WINDOW_S]
        return max(vals) if vals else None


# ---------------------------------------------------------------- conversion

def _frame_from_pcm(pcm: bytes, rate: int, channels: int) -> av.AudioFrame:
    a = np.frombuffer(pcm, dtype="<i2").reshape(1, -1)
    fr = av.AudioFrame.from_ndarray(a, format="s16", layout="mono" if channels == 1 else "stereo")
    fr.sample_rate = rate
    return fr


def _frames_to_bytes(frames) -> bytes:
    out = bytearray()
    for f in frames:
        out += bytes(f.planes[0])[: f.samples * 2 * len(f.layout.channels)]
    return bytes(out)


class PcmConverter:
    """Streaming s16 converter (any rate, mono/stereo -> mono at `out_rate`). Keeps
    resampler state between chunks, so chunked streams have no boundary clicks."""

    def __init__(self, rate: int, channels: int = 1, out_rate: int = RATE) -> None:
        if not isinstance(rate, int) or not 8000 <= rate <= 192000:
            raise ValueError(f"bad sample rate {rate!r}")
        if channels not in (1, 2):
            raise ValueError(f"bad channel count {channels!r}")
        self.rate, self.channels, self.out_rate = rate, channels, out_rate
        self._block = 2 * channels
        self._rest = b""
        self._rs = None if (rate == out_rate and channels == 1) else av.AudioResampler(
            format="s16", layout="mono", rate=out_rate)

    def convert(self, pcm: bytes) -> bytes:
        pcm = self._rest + bytes(pcm)
        n = len(pcm) - len(pcm) % self._block
        pcm, self._rest = pcm[:n], pcm[n:]
        if not pcm:
            return b""
        if self._rs is None:
            return pcm
        return _frames_to_bytes(self._rs.resample(_frame_from_pcm(pcm, self.rate, self.channels)))

    def flush(self) -> bytes:
        if self._rs is None:
            return b""
        return _frames_to_bytes(self._rs.resample(None))


def to_mono48(pcm: bytes, rate: int, channels: int = 1) -> bytes:
    c = PcmConverter(rate, channels)
    return c.convert(pcm) + c.flush()


def decode_file(path: str | os.PathLike, max_s: float = MAX_BUFFER_S) -> bytes:
    """Any audio file ffmpeg reads (wav, mp3, aiff, m4a...) -> mono s16 48 kHz PCM."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    out = bytearray()
    limit = int(max_s * RATE) * 2
    with av.open(str(p)) as c:
        streams = [s for s in c.streams if s.type == "audio"]
        if not streams:
            raise ValueError(f"no audio stream in {p.name}")
        rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        for frame in c.decode(streams[0]):
            frame.pts = None
            out += _frames_to_bytes(rs.resample(frame))
            if len(out) > limit:
                raise ValueError(f"{p.name} is longer than {max_s:.0f} s")
        out += _frames_to_bytes(rs.resample(None))
    return bytes(out)


def tone_pcm(freq: float = 880.0, seconds: float = 0.25, volume: float = 0.3) -> bytes:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    env = np.minimum(1.0, np.minimum(t, seconds - t) / 0.01)      # 10 ms fade in/out
    a = volume * 32767 * env * np.sin(2 * np.pi * freq * t)
    return a.astype("<i2").tobytes()


CHIME_FREQS = (660, 990)     # Hz, the two tones of chime_pcm()
CHIME_S = 0.6


def chime_pcm() -> bytes:
    """Short two-tone test sound (~0.6 s)."""
    gap = bytes(int(0.05 * RATE) * 2)
    return tone_pcm(CHIME_FREQS[0], 0.25) + gap + tone_pcm(CHIME_FREQS[1], 0.3)


def tts_macos(text: str, voice: str = "Alice", timeout_s: float = 20.0) -> bytes:
    """Offline text-to-speech with macOS `say` -> mono s16 48 kHz PCM.
    A stand-in for Grok TTS when testing. Raises RuntimeError when `say` is missing."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")
    if len(text) > MAX_SAY_CHARS:
        raise ValueError(f"text longer than {MAX_SAY_CHARS} characters")
    say = shutil.which("say")
    if say is None:
        raise RuntimeError("macOS `say` not found (TTS test only works on a Mac)")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "say.aiff"
        r = subprocess.run([say, "-v", voice, "-o", str(out), "--", text],
                           capture_output=True, text=True, timeout=timeout_s)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"say failed: {(r.stderr or r.stdout).strip() or r.returncode}")
        return decode_file(out)


def write_wav(path: str | os.PathLike, pcm: bytes, rate: int = RATE) -> str:
    """Atomic mono s16 WAV write (temp file + rename). Returns the absolute path."""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".tmp_{p.name}")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    os.replace(tmp, p)
    return str(p)


# ---------------------------------------------------------------- speaker

class SpeakerTrack(MediaStreamTrack):
    """Real-time 48 kHz mono audio track: queued PCM, else silence."""

    kind = "audio"

    def __init__(self, max_buffer_s: float = MAX_BUFFER_S) -> None:
        super().__init__()
        self._chunks: deque[bytes] = deque()
        self._head = 0                     # read offset into _chunks[0]
        self._bytes = 0
        self._max_bytes = int(max_buffer_s * RATE) * 2
        self._start: float | None = None
        self._pts = 0
        self.frames_sent = 0
        self.audio_frames_sent = 0         # frames that carried queued audio
        self._level = _Level()
        self.last_audio_t: float | None = None

    # ---- queue
    @property
    def buffered_s(self) -> float:
        return self._bytes / 2 / RATE

    @property
    def active(self) -> bool:
        return self._bytes > 0

    def enqueue(self, pcm48: bytes, *, max_lag_s: float | None = None) -> float:
        """Queue mono s16 48 kHz PCM. `max_lag_s` (live talk) drops the OLDEST queued
        audio so playback never lags more than that. Returns the seconds queued."""
        if self.readyState != "live":
            raise RuntimeError("speaker track stopped")
        pcm48 = bytes(pcm48)
        if len(pcm48) % 2:
            pcm48 = pcm48[:-1]
        if not pcm48:
            return self.buffered_s
        if self._bytes + len(pcm48) > self._max_bytes:
            raise OverflowError(f"speaker queue full (max {self._max_bytes / 2 / RATE:.0f} s)")
        self._chunks.append(pcm48)
        self._bytes += len(pcm48)
        if max_lag_s is not None:
            excess = self._bytes - int(max_lag_s * RATE) * 2
            if excess > 0:
                self._take(excess - excess % 2)
        return self.buffered_s

    def clear(self) -> None:
        self._chunks.clear()
        self._head = 0
        self._bytes = 0

    def _take(self, n: int) -> bytes:
        out = bytearray()
        while n > 0 and self._chunks:
            c = self._chunks[0]
            avail = len(c) - self._head
            k = min(n, avail)
            out += c[self._head:self._head + k]
            self._head += k
            n -= k
            if self._head >= len(c):
                self._chunks.popleft()
                self._head = 0
        self._bytes -= len(out)
        return bytes(out)

    def level_dbfs(self) -> float | None:
        return self._level.value()

    # ---- aiortc
    async def recv(self) -> av.AudioFrame:
        if self.readyState != "live":
            raise MediaStreamError
        now = time.monotonic()
        if self._start is None:
            self._start = now
        else:
            self._pts += FRAME_SAMPLES
            wait = self._start + self._pts / RATE - now
            if wait > 0:
                await asyncio.sleep(wait)
            elif wait < -0.5:              # event loop stalled: resync, don't burst
                self._start = now - self._pts / RATE
        if self.readyState != "live":
            raise MediaStreamError
        need = FRAME_SAMPLES * 2
        data = self._take(need)
        if data:
            self.audio_frames_sent += 1
            self.last_audio_t = time.monotonic()
            self._level.add(_dbfs(np.frombuffer(data, dtype="<i2")))
        if len(data) < need:
            data += bytes(need - len(data))
        frame = av.AudioFrame(format="s16", layout="mono", samples=FRAME_SAMPLES)
        frame.planes[0].update(data)
        frame.sample_rate = RATE
        frame.pts = self._pts
        frame.time_base = Fraction(1, RATE)
        self.frames_sent += 1
        return frame


# ---------------------------------------------------------------- microphone

class MicTap:
    """Receives the dog's audio frames; level meter + fan-out to subscriber queues."""

    def __init__(self) -> None:
        self._rs = None
        self._rs_key = None
        self.frames = 0
        self.last_t: float | None = None
        self.in_format: str | None = None
        self._level = _Level()
        self._subs: dict[asyncio.Queue, PcmConverter | None] = {}

    def _mono48(self, frame) -> bytes:
        key = (frame.format.name, frame.layout.name, frame.sample_rate)
        if key == ("s16", "mono", RATE):
            return bytes(frame.planes[0])[: frame.samples * 2]
        if self._rs is None or self._rs_key != key:
            self._rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
            self._rs_key = key
        frame.pts = None
        return _frames_to_bytes(self._rs.resample(frame))

    def feed(self, frame) -> None:
        pcm = self._mono48(frame)
        now = time.monotonic()
        self.frames += 1
        self.last_t = now
        self.in_format = f"{frame.format.name}/{frame.layout.name}/{frame.sample_rate}"
        if not pcm:
            return
        self._level.add(_dbfs(np.frombuffer(pcm, dtype="<i2")), now)
        for q, conv in list(self._subs.items()):
            data = pcm if conv is None else conv.convert(pcm)
            if not data:
                continue
            if q.full():                   # slow consumer: drop its oldest chunk
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(data)

    def subscribe(self, rate: int = RATE, max_chunks: int = 500) -> asyncio.Queue:
        """Queue of mono s16 chunks (~20 ms each) at `rate`. 500 chunks = ~10 s backlog."""
        q: asyncio.Queue = asyncio.Queue(maxsize=max_chunks)
        self._subs[q] = None if rate == RATE else PcmConverter(RATE, 1, out_rate=int(rate))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.pop(q, None)

    @property
    def subscribers(self) -> int:
        return len(self._subs)

    def level_dbfs(self) -> float | None:
        return self._level.value()

    def status(self) -> dict:
        now = time.monotonic()
        return {"frames": self.frames, "level_dbfs": self._level.value(now),
                "last_frame_age_s": round(now - self.last_t, 2) if self.last_t else None,
                "format": self.in_format}


async def collect(q: asyncio.Queue, seconds: float, rate: int,
                  first_timeout_s: float = 3.0) -> bytes:
    """Read `seconds` of mono s16 PCM from a MicTap queue. TimeoutError if nothing
    arrives within `first_timeout_s`; returns what it has if the stream stalls later."""
    need = int(seconds * rate) * 2
    got = bytearray()
    end_first = time.monotonic() + first_timeout_s
    end_all = end_first + seconds + 2.0
    while len(got) < need:
        deadline = end_first if not got else end_all
        left = deadline - time.monotonic()
        if left <= 0:
            if not got:
                raise TimeoutError("no audio from the dog's microphone")
            break
        try:
            got += await asyncio.wait_for(q.get(), left)
        except asyncio.TimeoutError:
            continue
    return bytes(got[:need])


def level_series(pcm: bytes, rate: int, window_s: float = 0.1) -> list[float]:
    """Per-window RMS dBFS of mono s16 PCM (for loopback evidence)."""
    a = np.frombuffer(pcm, dtype="<i2")
    w = max(1, int(rate * window_s))
    return [_dbfs(a[i:i + w]) for i in range(0, len(a), w)]


def tone_series(pcm: bytes, rate: int, freq: float, window_s: float = 0.1) -> list[float]:
    """Per-window strength of one frequency over the window's own 300-3000 Hz median, in dB.
    Finds a test tone under background noise, where plain loudness can't (a louder noise
    burst before the tone hides it). Digital silence gives 0 dB."""
    a = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    w = max(1, int(rate * window_s))
    fr = np.fft.rfftfreq(w, 1 / rate)
    near = (fr > freq - 15) & (fr < freq + 15)
    ref = (fr > 300) & (fr < 3000)
    win = np.hanning(w)
    out = []
    for i in range(0, len(a) - w + 1, w):
        sp = np.abs(np.fft.rfft(a[i:i + w] * win))
        out.append(round(20 * math.log10((sp[near].max() + 1e-6) / (np.median(sp[ref]) + 1e-6)), 1))
    return out


def loopback_check(pcm: bytes, rate: int, chime_at_s: float, chime_s: float = CHIME_S,
                   latency_s: float = 0.5, guard_s: float = 0.5, min_rise_db: float = 10.0,
                   window_s: float = 0.1) -> dict:
    """Did the mic hear chime_pcm()? For each chime tone: its strongest window while the
    chime plays (plus up to `latency_s` of path delay) minus its strongest window before
    the chime. Heard = every tone rose by at least `min_rise_db`.
    `guard_s`: the recording can start late (the mic switches on after the test clock
    starts), so the chime may land up to this much *before* `chime_at_s` in the recording.
    That stretch is never used as background, and the search for the tone starts there.
    On the real dog (2026-11-04) the tones rose ~29 and ~18 dB, ~0.2 s after sending."""
    before = max(1, int((chime_at_s - guard_s) / window_s))  # background: well before the chime
    end = int(math.ceil((chime_at_s + chime_s + latency_s) / window_s))
    rise = {}
    for f in CHIME_FREQS:
        s = tone_series(pcm, rate, f, window_s)
        pre, during = s[:before], s[before:end]
        rise[str(f)] = round(max(during) - max(pre), 1) if pre and during else 0.0
    return {"tone_rise_db": rise, "heard": all(v >= min_rise_db for v in rise.values()),
            "min_rise_db": min_rise_db}
