# Story → Anime Video (free & open-source pipeline)

A small web app: paste a story (or a scene-by-scene script), click generate, and get back
an MP4 anime-style video — narration, motion, captions and all — built entirely from
free / open-source components.

## Read this first: what "completely free" actually means here

There is no way to get Kling/Runway/Sora-quality anime video generation for $0 at
production scale — those run on huge paid GPU clusters. What *is* real and free:

- **Every model and library used below is open-source and free to run.**
- You need **compute** to run them. Two free options:
  1. **Your own GPU** (even a mid-range NVIDIA card with 6–8GB VRAM works for
     Stable-Diffusion-based anime art; more VRAM = faster/better).
  2. **A free cloud GPU notebook** — Google Colab or Kaggle both give free (rate-limited,
     session-capped) GPU time. See `colab/README.md`.
  3. If you have *no* GPU at all, the app still runs end-to-end using the built-in
     **Mock art provider** (fast placeholder illustrations) so you can test the whole
     pipeline, and swap in real Stable Diffusion later.
- This app is designed to be **self-hosted** (run on your machine or your free Colab
  session). "Free forever hosted on the internet for anyone" isn't realistic for
  GPU-heavy generation — Hugging Face Spaces' free GPU tier is the closest thing, and
  it sleeps/queues under load (documented below as an option).

## Pipeline (each stage is swappable)

```
Story text ──▶ [1] Scene Parser ──▶ [2] Image Gen (per scene) ──▶ [3] Motion (pan/zoom
or AnimateDiff) ──▶ [4] Narration TTS ──▶ [5] ffmpeg Assembly ──▶ final_video.mp4
```

| Stage | Free tool used | Needs GPU? |
|---|---|---|
| 1. Scene Parser | Rule-based splitter (default) or local [Ollama](https://ollama.com) LLM for smarter shot breakdown | No |
| 2. Image Gen | `MockProvider` (PIL placeholder art, default) or `StableDiffusionProvider` (`diffusers` + an anime checkpoint like Anything V5 / Counterfeit) | Mock: no. Real anime art: yes (or free Colab GPU) |
| 3. Motion | Ken Burns pan/zoom over each keyframe (default, works everywhere) or `AnimateDiff` / Stable Video Diffusion for actual generated motion | Ken Burns: no. AnimateDiff: yes |
| 4. Narration | `edge-tts` (Microsoft Edge's free TTS voices, no key, no GPU) | No |
| 5. Assembly | `ffmpeg` (concat clips, mux audio, burn captions) | No |

Every stage is a small Python module behind a simple interface (see `backend/pipeline/`),
so you can start with the free/no-GPU defaults, confirm the app works, then flip on
real Stable Diffusion / AnimateDiff once you have GPU access.

## Project layout

```
anime-video-app/
  backend/
    main.py                 Web server (Python stdlib only) + job orchestration
    pipeline/
      story_parser.py       story text -> list of scenes
      image_gen.py           scene -> keyframe image (Mock / Stable Diffusion)
      motion.py               keyframe(s) -> short video clip
      tts.py                   scene dialogue/narration -> audio
      assemble.py             clips + audio -> final mp4
      pipeline.py             runs all stages, tracks progress
    requirements.txt
  frontend/
    index.html               single-page UI, no build step needed
    app.js
    styles.css
  colab/
    README.md                how to run the GPU-heavy stages on free Colab
```

## Running it locally

```bash
cd anime-video-app/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt          # Pillow + edge-tts, that's it
python3 main.py                          # serves API + frontend together
```

Then open **http://localhost:8000/** in your browser. The backend is pure Python
standard library (`http.server`) — no FastAPI/Flask/uvicorn to install — and it
serves the frontend itself, so that one URL is all you need. Set `PORT=8080` (or
any port) as an env var before running if 8000 is taken.

### Telugu (and other Indian language) narration

Narration language defaults to **Telugu** (`te-IN`, voice `te-IN-ShrutiNeural`).
Change it per-request from the dropdown in the UI, or set the default with:

```bash
TTS_LANGUAGE=te-IN python3 main.py
```

Hindi, Tamil, Kannada, Malayalam, Marathi, Bengali, Indian/US English and Japanese
are wired up too (`backend/pipeline/tts.py` → `LANGUAGE_VOICES`) — add more with
`edge-tts --list-voices` to find any other free neural voice and its code.

### Switching on real anime art (Stable Diffusion)

1. `pip install diffusers transformers accelerate safetensors torch` (use the CUDA
   build of torch if you have an NVIDIA GPU: see https://pytorch.org/get-started/locally).
2. Download a free anime checkpoint, e.g. from Hugging Face / CivitAI (search
   "Anything V5", "Counterfeit-V3.0", "AnimePastelDream" — all free, open licenses,
   check each one's license terms before commercial use).
3. In `backend/pipeline/image_gen.py`, set `PROVIDER = "stable_diffusion"` and point
   `MODEL_PATH` at the checkpoint you downloaded.
4. Restart the backend. Generation will now be real anime-style art instead of
   placeholder cards (much slower without a GPU — minutes per image on CPU).

### Switching on real motion (AnimateDiff)

The Ken Burns default (pan/zoom over a still image) needs no extra setup and looks
fine for a "motion comic" style anime video. For actual generated in-between motion,
`backend/pipeline/motion.py` has a documented `AnimateDiffProvider` stub — wiring it up
needs `diffusers`' AnimateDiff pipeline and a GPU with ~12GB+ VRAM (or Colab).

## Realistic expectations

- Clip length per scene: a few seconds each is normal for free/open motion models.
  A 60-second video from ~10 scenes is a reasonable target.
- Generation time: Mock provider = seconds. Real Stable Diffusion on a consumer GPU =
  ~5–20s per image. AnimateDiff motion = 1–5 min per clip on a consumer GPU.
- Character consistency across scenes (the hard part of any anime generator, free or
  paid) is approximated here by keeping the same character description/seed across
  prompts — it will drift more than a paid, purpose-built tool.

## License note

You're responsible for checking the license of whichever checkpoint/model you plug
in (some anime checkpoints restrict commercial use). Everything scaffolded in this
repo (the app code itself) is yours to use and modify freely.
