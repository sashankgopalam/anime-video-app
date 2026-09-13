"""
Stage 4: turn a scene's dialogue/narration text into an audio file.

Default provider: `edge-tts` -- free, no API key, no signup, no GPU. It uses
Microsoft Edge's neural voices and fully supports Indian languages, including
**Telugu** (te-IN-ShrutiNeural / te-IN-MohanNeural), Hindi, Tamil, Kannada,
Malayalam, Bengali, Marathi, etc. Install with:

    pip install edge-tts

If edge-tts isn't installed, or the machine has no internet access at
generation time, we fall back to a silent clip of the right duration so the
pipeline never hard-fails -- you just get a video with no voice track instead
of a crash.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional, Protocol

# Language -> default free edge-tts voice. Add more from:
#   edge-tts --list-voices
LANGUAGE_VOICES = {
    "te-IN": "te-IN-ShrutiNeural",     # Telugu (female). Male alt: te-IN-MohanNeural
    "hi-IN": "hi-IN-SwaraNeural",      # Hindi
    "ta-IN": "ta-IN-PallaviNeural",    # Tamil
    "kn-IN": "kn-IN-SapnaNeural",      # Kannada
    "ml-IN": "ml-IN-SobhanaNeural",    # Malayalam
    "mr-IN": "mr-IN-AarohiNeural",     # Marathi
    "bn-IN": "bn-IN-TanishaaNeural",   # Bengali
    "en-IN": "en-IN-NeerjaNeural",     # Indian English
    "en-US": "en-US-AriaNeural",
    "ja-JP": "ja-JP-NanamiNeural",     # useful if you want Japanese narration
}

DEFAULT_LANGUAGE = os.environ.get("TTS_LANGUAGE", "te-IN")  # Telugu by default per project requirements
DEFAULT_VOICE = os.environ.get("TTS_VOICE", LANGUAGE_VOICES.get(DEFAULT_LANGUAGE, "en-US-AriaNeural"))


class TTSProvider(Protocol):
    def synthesize(self, text: str, out_path: Path, duration_hint: float = 4.0,
                    voice: Optional[str] = None) -> Path:
        ...


def _silent_clip(out_path: Path, duration_sec: float) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(max(0.5, duration_sec)),
        "-q:a", "9",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out_path


class EdgeTTSProvider:
    """Free neural TTS via Microsoft Edge's voices (edge-tts package)."""

    def synthesize(self, text: str, out_path: Path, duration_hint: float = 4.0,
                    voice: Optional[str] = None) -> Path:
        text = (text or "").strip()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not text:
            return _silent_clip(out_path, duration_hint)

        voice = voice or DEFAULT_VOICE
        try:
            import edge_tts

            async def _run():
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(str(out_path))

            asyncio.run(_run())
            if out_path.exists() and out_path.stat().st_size > 0:
                return out_path
            raise RuntimeError("edge-tts produced an empty file")
        except Exception:
            # Free tool not installed / no network at generation time / voice
            # unavailable -- never crash the whole video over the voice track.
            return _silent_clip(out_path, duration_hint)


def get_provider() -> TTSProvider:
    return EdgeTTSProvider()
