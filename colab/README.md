# Running the GPU-heavy stages on free Google Colab

Colab gives you a free (rate-limited, session-capped, no guarantee of availability)
NVIDIA GPU. This is the easiest free way to get **real** Stable-Diffusion anime art
and/or AnimateDiff motion if your own machine has no GPU.

There are two ways to use it with this app:

## Option A (simplest): generate art on Colab, assemble locally

1. Open a new Colab notebook, set **Runtime → Change runtime type → GPU**.
2. In a cell:
   ```python
   !pip install diffusers transformers accelerate safetensors
   from diffusers import StableDiffusionPipeline
   import torch

   pipe = StableDiffusionPipeline.from_pretrained(
       "stablediffusionapi/anything-v5",  # or any free anime checkpoint you prefer
       torch_dtype=torch.float16, safety_checker=None
   ).to("cuda")

   prompt = "a young ninja on a rooftop at sunset, anime style, cel shaded, studio anime key visual"
   image = pipe(prompt, width=768, height=432, num_inference_steps=25).images[0]
   image.save("scene_01.png")
   ```
3. Repeat per scene (loop over your scene prompts — you can copy them straight out
   of the app's scene breakdown), download the PNGs from Colab's file browser.
4. Drop those PNGs into your local job's `img_XXX.png` files (or just run the app
   with `IMAGE_PROVIDER=stable_diffusion` pointed at a local checkpoint instead —
   see the main README) and let the local app handle motion/voice/assembly.

## Option B: run the whole backend on Colab

1. Upload the `backend/` folder to your Colab session (or `git clone` your repo).
2. Install deps: `!pip install -r requirements.txt -r requirements-gpu.txt`
3. Set `IMAGE_PROVIDER=stable_diffusion` (and `SD_MODEL_PATH`) as environment
   variables, then run `!python3 main.py &`.
4. Expose it with a free tunnel so your browser can reach the Colab machine, e.g.
   [ngrok](https://ngrok.com) (free tier) or Colab's own `google.colab.output`
   port forwarding, then open the given URL.

Either way: Colab sessions are free but temporary (they disconnect after some
idle time / a max session length), so it's meant for batches of generation, not
an always-on server.
