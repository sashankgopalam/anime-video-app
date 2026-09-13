"""
Stage 5: stitch per-scene video+audio into one final MP4, with optional
burned-in captions. Pure ffmpeg -- free, no GPU, no extra Python deps.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from .story_parser import Scene


def mux_audio_video(video_path: Path, audio_path: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (mux) failed:\n{result.stderr[-2000:]}")
    return out_path


def concat_clips(clip_paths: List[Path], out_path: Path) -> Path:
    if not clip_paths:
        raise ValueError("No clips to concatenate")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.parent / f"{out_path.stem}_concat_list.txt"
    with open(list_file, "w") as f:
        for clip in clip_paths:
            f.write(f"file '{clip.resolve()}'\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (concat) failed:\n{result.stderr[-2000:]}")
    return out_path


def _srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(scenes: List[Scene], durations: List[float], out_path: Path) -> Path:
    """One caption per scene (dialogue if present, else the scene description),
    timed against each scene's actual clip duration."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    t = 0.0
    for i, (scene, dur) in enumerate(zip(scenes, durations), start=1):
        text = (scene.dialogue or scene.description).strip()
        if not text:
            t += dur
            continue
        start, end = t, t + dur
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
        t = end
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def burn_captions(video_path: Path, srt_path: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # subtitles filter path needs escaping on some ffmpeg builds; keep it simple
    # by running ffmpeg with cwd set to the srt's directory.
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path.resolve()),
        "-vf", f"subtitles={srt_path.name}:force_style='FontName=DejaVu Sans,FontSize=16,PrimaryColour=&HFFFFFF&,BorderStyle=3,Outline=1,Shadow=0,MarginV=55'",
        "-c:a", "copy",
        str(out_path.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(srt_path.parent))
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (captions) failed:\n{result.stderr[-2000:]}")
    return out_path


def assemble_video(
    scene_clip_paths: List[Path],
    scene_audio_paths: List[Path],
    scene_durations: List[float],
    scenes: List[Scene],
    work_dir: Path,
    final_out_path: Path,
    with_captions: bool = True,
) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)

    muxed_clips = []
    for i, (clip, audio) in enumerate(zip(scene_clip_paths, scene_audio_paths)):
        muxed = work_dir / f"muxed_{i:03d}.mp4"
        muxed_clips.append(mux_audio_video(clip, audio, muxed))

    concatenated = work_dir / "concatenated.mp4"
    concat_clips(muxed_clips, concatenated)

    if not with_captions:
        concatenated.replace(final_out_path)
        return final_out_path

    srt_path = work_dir / "captions.srt"
    build_srt(scenes, scene_durations, srt_path)
    try:
        burn_captions(concatenated, srt_path, final_out_path)
    except RuntimeError:
        # captions are a nice-to-have; never let them block delivering the video
        concatenated.replace(final_out_path)
    return final_out_path
