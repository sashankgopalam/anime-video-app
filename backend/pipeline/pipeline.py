"""
Orchestrates all 5 stages for one job and reports progress as it goes.
Deliberately dependency-free beyond the other pipeline modules, so it runs
the same way whether the optional heavy providers (Stable Diffusion,
AnimateDiff, edge-tts) are installed or not.
"""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import image_gen, motion, tts, assemble
from .story_parser import Scene, parse_story

JOBS_DIR = Path(__file__).resolve().parent.parent / "jobs_storage"
MIN_SCENE_DURATION = 2.5


@dataclass
class JobState:
    id: str
    title: str
    status: str = "queued"       # queued | running | done | error
    stage: str = ""
    progress: float = 0.0         # 0..100
    scenes_total: int = 0
    scenes_done: int = 0
    error: Optional[str] = None
    video_path: Optional[Path] = None
    created_at: float = field(default_factory=time.time)


_jobs: dict[str, JobState] = {}
_jobs_lock = threading.Lock()


def create_job(title: str, story_text: str, language: str = "te-IN", max_scenes: int = 12) -> JobState:
    job_id = uuid.uuid4().hex[:12]
    job = JobState(id=job_id, title=title or "Untitled")
    with _jobs_lock:
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_job, args=(job, story_text, language, max_scenes), daemon=True
    )
    thread.start()
    return job


def get_job(job_id: str) -> Optional[JobState]:
    with _jobs_lock:
        return _jobs.get(job_id)


def _audio_duration_sec(path: Path) -> float:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return max(MIN_SCENE_DURATION, float(out))
    except Exception:
        return MIN_SCENE_DURATION


def _run_job(job: JobState, story_text: str, language: str, max_scenes: int) -> None:
    job_dir = JOBS_DIR / job.id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        job.status = "running"
        job.stage = "parsing story into scenes"
        job.progress = 2
        parsed = parse_story(story_text, title=job.title, max_scenes=max_scenes)
        scenes: List[Scene] = parsed.scenes
        if not scenes:
            raise ValueError("Couldn't find any scenes in that story text.")
        job.scenes_total = len(scenes)

        img_provider = image_gen.get_provider()
        motion_provider = motion.get_provider()
        tts_provider = tts.get_provider()
        voice = tts.LANGUAGE_VOICES.get(language, tts.DEFAULT_VOICE)

        clip_paths, audio_paths, durations = [], [], []

        per_scene_pct = 85 / max(1, len(scenes))
        for scene in scenes:
            job.stage = f"scene {scene.index + 1}/{len(scenes)}: drawing keyframe"
            img_path = job_dir / f"img_{scene.index:03d}.png"
            img_provider.generate(scene, img_path)

            job.stage = f"scene {scene.index + 1}/{len(scenes)}: narrating ({language})"
            audio_path = job_dir / f"aud_{scene.index:03d}.mp3"
            narration_text = scene.dialogue or scene.description
            tts_provider.synthesize(narration_text, audio_path, duration_hint=4.0, voice=voice)
            duration = _audio_duration_sec(audio_path)

            job.stage = f"scene {scene.index + 1}/{len(scenes)}: animating"
            clip_path = job_dir / f"clip_{scene.index:03d}.mp4"
            motion_provider.generate_clip(img_path, clip_path, duration, seed_text=scene.description)

            clip_paths.append(clip_path)
            audio_paths.append(audio_path)
            durations.append(duration)

            job.scenes_done += 1
            job.progress = min(90.0, 2 + per_scene_pct * job.scenes_done)

        job.stage = "assembling final video"
        job.progress = 92
        final_path = job_dir / "final_video.mp4"
        assemble.assemble_video(
            clip_paths, audio_paths, durations, scenes,
            work_dir=job_dir / "work",
            final_out_path=final_path,
        )

        job.video_path = final_path
        job.stage = "done"
        job.progress = 100
        job.status = "done"
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        job.status = "error"
        job.error = str(exc)
        job.stage = "failed"
