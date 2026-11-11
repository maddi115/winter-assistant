"""Hearing the streamer - as a HINT for chat, never the only reason to speak.

  streamlink (audio only) -> ffmpeg (16kHz mono) -> voice detection (Silero VAD, CPU)
  -> Moonshine speech-to-text (moonshine-voice, CPU, ~1 core, ~0.5GB RAM, no GPU) -> junk filter -> keywords
  -> ECHO CHECK: a heard word only counts once chat or the stream title says it too.

Noise defenses: music / game sounds / silence aren't transcribed (VAD), lyric-like or "imagined"
lines are dropped (junk filter), only keywords are used (one misheard word doesn't matter),
and if it's mostly junk for a few minutes, hearing pauses itself.
Nothing is saved: only the last ~60s of text, in memory.
"""
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from collections import deque

import numpy as np

from twitch.chatflow import topic_words

RATE = 16000
IMAGINED = ["thanks for watching", "thank you for watching", "please subscribe", "like and subscribe",
            "see you next time", "subtitles by", "transcribed by", "you you you", "bye bye bye"]


def is_junk(text: str) -> str:
    """Why this transcript is junk ('' = it's fine)."""
    t = (text or "").strip()
    low = t.lower()
    if not t:
        return "empty"
    if "♪" in t or re.search(r"[\[(](music|applause|laughter|silence|inaudible)[\])]", low):
        return "music"
    words = re.findall(r"[a-z']+", low)
    if len(words) < 2:
        return "too short"
    if any(p in low for p in IMAGINED):
        return "imagined phrase"
    if len(words) >= 6 and len(set(words)) / len(words) < 0.5:
        return "repeats (lyrics?)"
    if not topic_words(t):
        return "no real words"
    return ""


class Transcript:
    """The last ~60s of what the streamer said, plus the echo check against chat + title."""

    def __init__(self, keep=60, clock=time.time, health_window=20, pause_sec=180):
        self.keep, self.clock = keep, clock
        self.items = deque()                  # (time, text, words)
        self.results = deque(maxlen=health_window)   # True = junk
        self.paused_until = 0.0
        self.pause_sec = pause_sec
        self.log = None

    def add(self, text, why_junk=None):
        """Feed one transcribed piece. Returns True if kept."""
        now = self.clock()
        why = is_junk(text) if why_junk is None else why_junk
        self.results.append(bool(why))
        self._health(now)
        while self.items and now - self.items[0][0] > self.keep:
            self.items.popleft()
        if why or now < self.paused_until:
            return False
        self.items.append((now, text.strip(), topic_words(text)))
        return True

    def _health(self, now):
        if len(self.results) >= 12 and sum(self.results) / len(self.results) > 0.7 and now >= self.paused_until:
            self.paused_until = now + self.pause_sec
            self.items.clear()
            self.results.clear()
            if self.log:
                self.log(f"🔇 audio is mostly noise/music - ignoring it for {self.pause_sec // 60} min")

    @property
    def paused(self):
        return self.clock() < self.paused_until

    def heard_words(self):
        now = self.clock()
        return set().union(*(w for t, _, w in self.items if now - t <= self.keep)) if self.items else set()

    def trusted(self, room, chat_window=60):
        """Heard words that chat or the stream title ALSO says (echo check)."""
        heard = self.heard_words()
        if not heard or self.paused:
            return set()
        cut = room.clock() - chat_window
        chat = set().union(*(topic_words(l.text) for l in room.lines if not l.is_bot and l.ts >= cut)) \
            if room.lines else set()
        chat |= topic_words(getattr(room, "stream", "") or "")
        return heard & chat

    def snippets(self, room, n=2):
        """What the streamer said that's backed by chat - for the AI, marked as maybe-misheard."""
        trusted = self.trusted(room)
        if not trusted:
            return []
        hits = [txt for _, txt, w in self.items if w & trusted]
        return [h[:140] for h in hits[-n:]]


class Transcriber:
    """Moonshine on the CPU. New package `moonshine-voice` (pip install moonshine-voice);
    falls back to the old `useful-moonshine-onnx` if that's what's installed."""

    def __init__(self, model="moonshine/base", language="en", arch=None):
        self.kind = None
        try:
            from moonshine_voice import Transcriber as MV, get_model_for_language
            path, default_arch = get_model_for_language(language)     # downloads once, then cached
            self.t = MV(model_path=path, model_arch=arch if arch is not None else default_arch)
            self.kind = "moonshine-voice"
        except ImportError:
            import moonshine_onnx                                      # old package
            self.m, self.model, self.kind = moonshine_onnx, model, "moonshine-onnx"

    def __call__(self, audio):
        audio = np.asarray(audio, dtype=np.float32)
        if self.kind == "moonshine-voice":
            out = self.t.transcribe_without_streaming(audio, sample_rate=RATE)
            return " ".join(l.text for l in getattr(out, "lines", []) if getattr(l, "text", "")).strip()
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            with wave.open(f.name, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
            out = self.m.transcribe(f.name, self.model)
        return out[0] if isinstance(out, (list, tuple)) else str(out)


class VoiceGate:
    """Silero VAD: only stretches that sound like speech get transcribed."""

    def __init__(self):
        import torch
        from silero_vad import load_silero_vad, get_speech_timestamps
        self.torch, self.model, self.ts = torch, load_silero_vad(), get_speech_timestamps

    def speech(self, audio):
        """-> (speech-only audio, share of the window that was speech)"""
        segs = self.ts(self.torch.from_numpy(audio).float(), self.model, sampling_rate=RATE)
        if not segs:
            return np.zeros(0, dtype=np.float32), 0.0
        parts = [audio[s["start"]:s["end"]] for s in segs]
        speech = np.concatenate(parts)
        return speech, len(speech) / max(1, len(audio))


def process_window(audio, gate, transcribe, transcript, min_speech=0.25):
    """One ~8s window: VAD -> (maybe) speech-to-text -> transcript. Returns what happened (for logs/tests)."""
    speech, share = gate(audio) if callable(gate) else gate.speech(audio)
    if share < min_speech or len(speech) < RATE // 2:
        transcript.add("", why_junk="not speech (music / game / silence)")
        return "skipped: not speech"
    try:
        text = transcribe(speech[: RATE * 15])
    except Exception as e:
        transcript.add("", why_junk=f"error {e}")
        return f"error: {e}"
    kept = transcript.add(text)
    return f"heard: {text!r}" + ("" if kept else f" (dropped: {is_junk(text) or 'paused'})")


class Hearing:
    """Background listener for one channel. Restarts by itself; quietly waits while the stream is offline."""

    def __init__(self, channel, config, transcript, log=print):
        self.channel, self.c, self.t, self.log = channel, config, transcript, log
        self.t.log = log
        self.stop_flag = threading.Event()
        self.thread = None

    @staticmethod
    def missing():
        need = [x for x in ("streamlink", "ffmpeg") if not shutil.which(x)]
        try:
            __import__("silero_vad")
        except Exception:
            need.append("silero-vad")
        for mod in ("moonshine_voice", "moonshine_onnx"):          # either works
            try:
                __import__(mod)
                break
            except Exception:
                continue
        else:
            need.append("moonshine-voice")
        return need

    def start(self):
        miss = self.missing()
        if miss:
            self.log(f"🎧 #{self.channel}: can't listen, missing {', '.join(miss)} (see README)")
            return False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_flag.set()

    def _run(self):
        try:
            gate = VoiceGate()
            transcribe = Transcriber(self.c.twitch_audio_model, arch=self.c.twitch_audio_arch)
        except Exception as e:
            self.log(f"🎧 #{self.channel}: couldn't load speech models ({e})")
            return
        self.log(f"🎧 #{self.channel}: listening to the streamer ({transcribe.kind}, CPU)")
        win = int(RATE * self.c.twitch_audio_window) * 2          # bytes (int16)
        while not self.stop_flag.is_set():
            sl = ff = None
            try:
                sl = subprocess.Popen(["streamlink", "--stdout", "--twitch-disable-ads",
                                       f"https://twitch.tv/{self.channel}", "audio_only,worst"],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                ff = subprocess.Popen(["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0", "-f", "s16le", "-ac", "1",
                                       "-ar", str(RATE), "pipe:1"], stdin=sl.stdout, stdout=subprocess.PIPE)
                while not self.stop_flag.is_set():
                    raw = ff.stdout.read(win)
                    if not raw or len(raw) < win // 4:
                        break                                     # stream ended / offline
                    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    if not self.t.paused:
                        process_window(audio, gate, transcribe, self.t, self.c.twitch_audio_min_speech)
            except Exception as e:
                self.log(f"🎧 #{self.channel}: audio error ({e}) - retrying")
            finally:
                for p in (ff, sl):
                    if p:
                        p.kill()
            self.stop_flag.wait(120)                              # offline -> check again in 2 min
