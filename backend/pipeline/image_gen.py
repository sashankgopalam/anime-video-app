"""
Stage 2: turn one Scene into a keyframe image.

Two providers behind the same interface:

- MockProvider (default, always available): renders a stylized placeholder
  "storyboard panel" with Pillow. No GPU, no downloads, no network. This is
  what proves the pipeline works end-to-end on any machine, including one
  with no GPU at all.

- StableDiffusionProvider: real anime-style art via `diffusers` + an anime
  checkpoint. Needs the extra deps in requirements-gpu.txt and, realistically,
  a GPU (local or free Colab) to run at a usable speed. See README.md.

Flip providers with the PROVIDER env var or the `PROVIDER` constant below.
"""
from __future__ import annotations

import hashlib
import os
import textwrap
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .story_parser import Scene

PROVIDER = os.environ.get("IMAGE_PROVIDER", "mock")  # "mock" | "stable_diffusion"
SD_MODEL_PATH = os.environ.get("SD_MODEL_PATH", "")  # set to a local checkpoint dir/file
IMAGE_SIZE = (768, 432)  # 16:9


class ImageProvider(Protocol):
    def generate(self, scene: Scene, out_path: Path) -> Path:
        ...


def _palette_for(text: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Deterministic but varied gradient colors, seeded from the scene text so
    the same scene always renders the same way, and different scenes look
    different from each other."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    top = (60 + h[0] % 150, 60 + h[1] % 150, 90 + h[2] % 150)
    bottom = (20 + h[3] % 100, 20 + h[4] % 100, 40 + h[5] % 120)
    return top, bottom


def _vertical_gradient(size, top, bottom) -> Image.Image:
    w, h = size
    base = Image.new("RGB", (1, h), color=0)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.point((0, y), fill=color)
    return base.resize(size)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class MockProvider:
    """Free, offline, no-GPU placeholder art generator."""

    def generate(self, scene: Scene, out_path: Path) -> Path:
        top, bottom = _palette_for(scene.description or f"scene-{scene.index}")
        img = _vertical_gradient(IMAGE_SIZE, top, bottom)
        img = img.filter(ImageFilter.GaussianBlur(1))
        draw = ImageDraw.Draw(img)

        # simple "sun/moon" disc + a couple of silhouette shapes for a bit of
        # visual variety between scenes, purely decorative
        h = hashlib.sha256((scene.description or "").encode()).digest()
        cx, cy = IMAGE_SIZE[0] * (0.15 + 0.7 * (h[6] / 255)), IMAGE_SIZE[1] * 0.25
        r = 40 + h[7] % 30
        disc_color = (240, 230, 200) if h[8] % 2 == 0 else (255, 200, 190)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=disc_color)

        ground_y = IMAGE_SIZE[1] * 0.75
        draw.polygon(
            [
                (0, IMAGE_SIZE[1]),
                (0, ground_y),
                (IMAGE_SIZE[0] * 0.3, ground_y - 20),
                (IMAGE_SIZE[0] * 0.6, ground_y + 10),
                (IMAGE_SIZE[0], ground_y - 30),
                (IMAGE_SIZE[0], IMAGE_SIZE[1]),
            ],
            fill=(20, 20, 30),
        )

        # scene text caption, wrapped, bottom third, with a translucent panel
        caption = scene.description.strip() or "(scene)"
        wrapped = textwrap.fill(caption, width=46)
        font = _load_font(22)
        panel_h = 18 * (wrapped.count("\n") + 1) + 30
        overlay = Image.new("RGBA", IMAGE_SIZE, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle(
            [0, IMAGE_SIZE[1] - panel_h, IMAGE_SIZE[0], IMAGE_SIZE[1]],
            fill=(0, 0, 0, 150),
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.multiline_text(
            (16, IMAGE_SIZE[1] - panel_h + 10), wrapped, font=font, fill=(255, 255, 255)
        )
        draw.text(
            (IMAGE_SIZE[0] - 130, 10),
            f"scene {scene.index + 1}",
            font=_load_font(16),
            fill=(255, 255, 255, 180),
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, quality=92)
        return out_path


class StableDiffusionProvider:
    """Real anime art via free/open Stable Diffusion weights (diffusers).

    Requires: pip install diffusers transformers accelerate safetensors torch
    and a downloaded anime checkpoint (see README.md for free options).
    Loading the model is deferred to first use so importing this module never
    requires torch/diffusers to be installed.
    """

    def __init__(self, model_path: str):
        if not model_path:
            raise ValueError(
                "SD_MODEL_PATH is not set. Point it at a local Stable Diffusion "
                "checkpoint or a Hugging Face repo id (see README.md for free "
                "options) before using the stable_diffusion provider."
            )
        self.model_path = model_path
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            import torch
            from diffusers import StableDiffusionPipeline

            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():  # Apple Silicon GPU
                device = "mps"
            else:
                device = "cpu"

            # fp16 is unreliable on MPS (can produce black images with some
            # ops) and CPU doesn't support it at all -- only use it on CUDA.
            dtype = torch.float16 if device == "cuda" else torch.float32
            self._pipe = StableDiffusionPipeline.from_pretrained(
                self.model_path,
                torch_dtype=dtype,
                safety_checker=None,
            ).to(device)
        return self._pipe

    def generate(self, scene: Scene, out_path: Path) -> Path:
        pipe = self._pipeline()
        image = pipe(
            scene.image_prompt,
            negative_prompt="lowres, blurry, extra limbs, watermark, text",
            width=IMAGE_SIZE[0],
            height=IMAGE_SIZE[1],
            num_inference_steps=25,
        ).images[0]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)
        return out_path


def get_provider() -> ImageProvider:
    if PROVIDER == "stable_diffusion":
        return StableDiffusionProvider(SD_MODEL_PATH)
    return MockProvider()
