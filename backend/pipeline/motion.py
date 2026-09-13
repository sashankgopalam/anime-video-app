"""
Stage 3: turn one keyframe image into a short video clip with motion.

Default: Ken Burns pan/zoom via ffmpeg's `zoompan` filter. This needs nothing
but ffmpeg (already free/open-source, no GPU, works everywhere) and gives a
"motion comic" / anime-PV feel that's a completely reasonable free substitute
for full generated motion.

Optional upgrade: AnimateDiffProvider (stub below) for real in-betweened
motion via diffusers' AnimateDiff pipeline. Needs a GPU with ~12GB+ VRAM
(local or free Colab) -- see README.md.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Protocol

PROVIDER = os.environ.get("MOTION_PROVIDER", "ken_burns")  # "ken_burns" | "animatediff"
FPS = 24


class MotionProvider(Protocol):
    def generate_clip(self, image_path: Path, out_path: Path, duration_sec: float, seed_text: str = "") -> Path:
        ...


class KenBurnsProvider:
    def generate_clip(self, image_path: Path, out_path: Path, duration_sec: float, seed_text: str = "") -> Path:
        duration_sec = max(1.0, float(duration_sec))
        total_frames = max(1, int(duration_sec * FPS))

        # Alternate zoom-in / zoom-out and pan direction per scene, deterministically,
        # so scenes visibly differ from each other but are reproducible.
        h = hashlib.sha256((seed_text or str(image_path)).encode()).digest()
        zoom_in = h[0] % 2 == 0
        pan_x = ["iw/2-(iw/zoom/2)", "0", "iw-(iw/zoom)"][h[1] % 3]
        pan_y = ["ih/2-(ih/zoom/2)", "0", "ih-(ih/zoom)"][h[2] % 3]

        if zoom_in:
            zoom_expr = f"min(zoom+0.0012,1.25)"
        else:
            zoom_expr = f"if(eq(on,0),1.25,max(zoom-0.0012,1.0))"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        vf = (
            f"scale=1536:864,"
            f"zoompan=z='{zoom_expr}':x='{pan_x}':y='{pan_y}':d={total_frames}:s=768x432:fps={FPS},"
            f"format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", vf,
            "-t", str(duration_sec),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg (Ken Burns) failed:\n{result.stderr[-2000:]}")
        return out_path


class AnimateDiffProvider:
    """Stub: wire this up once you have GPU access.

    pip install diffusers transformers accelerate safetensors torch
    Then load an AnimateDiff motion-adapter + your SD checkpoint via
    diffusers.AnimateDiffPipeline and export frames with
    diffusers.utils.export_to_video. See:
    https://huggingface.co/docs/diffusers/api/pipelines/animatediff
    """

    def generate_clip(self, image_path: Path, out_path: Path, duration_sec: float, seed_text: str = "") -> Path:
        raise NotImplementedError(
            "AnimateDiffProvider is a stub -- see the docstring / README.md for how "
            "to wire up real generated motion once you have GPU access."
        )


def get_provider() -> MotionProvider:
    if PROVIDER == "animatediff":
        return AnimateDiffProvider()
    return KenBurnsProvider()
