"""
Zero-extra-dependency backend server (stdlib http.server only) so the app
runs on any machine with just Python 3 + ffmpeg installed -- no pip install
headaches for the web layer itself. The optional heavy stages (real Stable
Diffusion art, real edge-tts voices) bring their own deps, documented in
README.md, and degrade gracefully to free no-GPU fallbacks when absent.

Run:
    python3 main.py            # serves the API + the frontend on :8000
Then open http://localhost:8000/ in a browser.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import pipeline, tts  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
PORT = int(os.environ.get("PORT", "8000"))

JOB_ID_RE = re.compile(r"^/api/jobs/([a-f0-9]{6,32})$")
JOB_VIDEO_RE = re.compile(r"^/api/jobs/([a-f0-9]{6,32})/video$")


def _json_bytes(obj) -> bytes:
    return json.dumps(obj, default=str).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "AnimeVideoApp/0.1"

    def log_message(self, fmt, *args):  # quieter default logging
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    # ---- helpers -------------------------------------------------
    def _send_json(self, status: int, payload) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def _serve_static(self, rel_path: str) -> None:
        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        file_path = (FRONTEND_DIR / rel_path).resolve()
        if FRONTEND_DIR.resolve() not in file_path.parents and file_path != FRONTEND_DIR.resolve():
            self._send_json(403, {"error": "forbidden"})
            return
        if not file_path.exists() or not file_path.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _serve_video(self, job_id: str) -> None:
        job = pipeline.get_job(job_id)
        if not job or not job.video_path or not Path(job.video_path).exists():
            self._send_json(404, {"error": "video not ready"})
            return
        path = Path(job.video_path)
        file_size = path.stat().st_size
        range_header = self.headers.get("Range")

        start, end = 0, file_size - 1
        status = 200
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if match:
                status = 206
                start = int(match.group(1)) if match.group(1) else 0
                end = int(match.group(2)) if match.group(2) else file_size - 1

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self._cors()
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            chunk = 1024 * 256
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)

    # ---- HTTP verbs ------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/languages":
            self._send_json(200, {"languages": tts.LANGUAGE_VOICES, "default": tts.DEFAULT_LANGUAGE})
            return

        match = JOB_VIDEO_RE.match(path)
        if match:
            self._serve_video(match.group(1))
            return

        match = JOB_ID_RE.match(path)
        if match:
            job = pipeline.get_job(match.group(1))
            if not job:
                self._send_json(404, {"error": "job not found"})
                return
            self._send_json(200, {
                "id": job.id,
                "title": job.title,
                "status": job.status,
                "stage": job.stage,
                "progress": job.progress,
                "scenes_total": job.scenes_total,
                "scenes_done": job.scenes_done,
                "error": job.error,
                "video_ready": bool(job.video_path and Path(job.video_path).exists()),
            })
            return

        if path.startswith("/api/"):
            self._send_json(404, {"error": "not found"})
            return

        self._serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/jobs":
            try:
                body = self._read_json_body()
                title = str(body.get("title") or "Untitled")
                story = str(body.get("story") or "").strip()
                language = str(body.get("language") or tts.DEFAULT_LANGUAGE)
                max_scenes = int(body.get("max_scenes") or 12)
                if not story:
                    self._send_json(400, {"error": "story text is required"})
                    return
                job = pipeline.create_job(title, story, language=language, max_scenes=max_scenes)
                self._send_json(202, {"id": job.id, "status": job.status})
            except Exception as exc:  # noqa: BLE001
                self._send_json(400, {"error": str(exc)})
            return

        self._send_json(404, {"error": "not found"})


def main():
    pipeline.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Anime video app running: http://localhost:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
