"""
Stage 1: turn raw story/scene text into a structured list of Scene objects.

Free by default: a rule-based splitter, no external calls, no GPU.
Optional upgrade: if a local Ollama server is running (https://ollama.com, free,
runs on CPU or GPU), we ask it to do a smarter scene/shot breakdown and write
better image prompts. If Ollama isn't reachable, we silently fall back to the
rule-based splitter -- the app never hard-fails because an optional free tool
isn't installed.
"""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Optional

ANIME_STYLE_SUFFIX = (
    "anime style, cel shaded, vibrant colors, detailed background, "
    "studio anime key visual, consistent character design"
)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1"  # any locally-pulled free Ollama model works


@dataclass
class Scene:
    index: int
    description: str            # what happens in the scene (used to build the image prompt)
    dialogue: str = ""           # spoken line(s), narrated via TTS if present
    duration_sec: float = 4.0    # target length of this scene's video clip
    image_prompt: str = ""       # final prompt sent to the image generator

    def __post_init__(self):
        if not self.image_prompt:
            self.image_prompt = f"{self.description.strip()}, {ANIME_STYLE_SUFFIX}"


@dataclass
class ParsedStory:
    title: str
    scenes: List[Scene] = field(default_factory=list)


_SCENE_MARKER_RE = re.compile(r"^\s*(scene|shot)\s*\d*\s*[:.\-]\s*", re.IGNORECASE)
_DIALOGUE_RE = re.compile(r'"([^"]+)"|“([^”]+)”')


def _split_rule_based(raw_text: str, max_scenes: int = 20) -> List[Scene]:
    """No dependencies, no network. Splits on blank lines / explicit 'Scene N:'
    markers; falls back to sentence grouping if the user just pasted one big
    paragraph."""
    raw_text = raw_text.strip()
    if not raw_text:
        return []

    # Prefer explicit paragraph breaks (most natural way to type "one scene per block")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw_text) if b.strip()]

    if len(blocks) == 1:
        # Single blob of text -- group sentences into chunks of ~2-3 sentences per scene
        sentences = re.split(r"(?<=[.!?])\s+", blocks[0])
        chunk_size = 2
        blocks = [
            " ".join(sentences[i : i + chunk_size]).strip()
            for i in range(0, len(sentences), chunk_size)
            if " ".join(sentences[i : i + chunk_size]).strip()
        ]

    blocks = blocks[:max_scenes]

    scenes: List[Scene] = []
    for i, block in enumerate(blocks):
        block = _SCENE_MARKER_RE.sub("", block).strip()
        dialogue_matches = _DIALOGUE_RE.findall(block)
        dialogue = " ".join(next(g for g in m if g) for m in dialogue_matches) if dialogue_matches else ""
        description = _DIALOGUE_RE.sub("", block).strip() or block
        scenes.append(
            Scene(
                index=i,
                description=description,
                dialogue=dialogue,
            )
        )
    return scenes


def _try_ollama_breakdown(raw_text: str, max_scenes: int) -> Optional[List[Scene]]:
    """Best-effort call to a local free Ollama server for a smarter breakdown.
    Returns None (never raises) if Ollama isn't running or the response is
    malformed, so the caller can fall back cleanly."""
    system = (
        "You are a storyboard artist. Break the given story into at most "
        f"{max_scenes} short scenes for an anime video. Reply with ONLY a JSON "
        'array like [{"description": "...", "dialogue": "..."}]. "description" '
        'is a vivid visual description for an image generator (setting, action, '
        'mood, character appearance). "dialogue" is the spoken line for that '
        'scene, or an empty string if none.'
    )
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": f"{system}\n\nSTORY:\n{raw_text}\n\nJSON:",
            "stream": False,
        }
    ).encode("utf-8")

    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body.get("response", "")
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return None
        items = json.loads(match.group(0))
        scenes = [
            Scene(
                index=i,
                description=str(item.get("description", "")).strip(),
                dialogue=str(item.get("dialogue", "")).strip(),
            )
            for i, item in enumerate(items[:max_scenes])
            if item.get("description")
        ]
        return scenes or None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None


def parse_story(raw_text: str, title: str = "Untitled", max_scenes: int = 20,
                 use_ollama: bool = True) -> ParsedStory:
    scenes: Optional[List[Scene]] = None
    if use_ollama:
        scenes = _try_ollama_breakdown(raw_text, max_scenes)
    if not scenes:
        scenes = _split_rule_based(raw_text, max_scenes)
    return ParsedStory(title=title, scenes=scenes)
