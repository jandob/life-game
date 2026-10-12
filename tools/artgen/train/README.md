# train: character LoRA for SDXL (WAI v17) on Apple Silicon

Trial result: a rank-16 LoRA trained on 26 FLUX-klein images of one adult woman keeps hair, outfit colours
and general look across new scenes. Everything heavy lives outside the repo (`~/.cache/artgen/`); LoRA weights are not in git.

```
train/train_dreambooth_lora_sdxl.py  diffusers example (Apache-2.0, commit 85c9fa4 = installed diffusers), + "# LG:" patches
train/run_train.sh                   the exact flags used (OUTPUT_DIR MAX_STEPS)
train/convert_single_file.py         single .safetensors -> diffusers folder (the trainer needs a folder)
train/make_dataset.py                gen | pack | sheet for the lgwoman1 dataset
train/eval_lora.py                   evaluation grid + sheet
```
Extra packages in `.venv` (installed with `python3 -m pip --python .venv/bin/python install datasets tensorboard torchvision`,
+284 MB: pyarrow, pandas, grpcio, aiohttp...). It downgraded fsspec 2026.9.0 -> 2026.7.0 (datasets pin).
Local patches to the trainer: `--cache_latents` (lazy, needs `--center_crop`; this diffusers commit has no such flag) and MPS memory
in the progress bar. fp16/bf16 are off: fp32 only.

## Steps (all from `tools/artgen`, no network needed after the models are cached)

```sh
# 1. WAI v17 single file -> diffusers folder (6.5 GB, fp16 weights, 8 s). Source file is only read.
.venv/bin/python train/convert_single_file.py ~/Downloads/waiIllustriousSDXL_v170.safetensors ~/.cache/artgen/wai_v17_diffusers

# 2. dataset: FLUX klein --ref images (28 specs; ~113 s each while the GPU was shared) -> square pad/crop + captions
.venv/bin/python train/make_dataset.py gen  --ref REF.png --raw ~/.cache/artgen/datasets/lgwoman1_raw
.venv/bin/python train/make_dataset.py pack --raw ~/.cache/artgen/datasets/lgwoman1_raw --out ~/.cache/artgen/datasets/lgwoman1
.venv/bin/python train/make_dataset.py sheet --out ~/.cache/artgen/datasets/lgwoman1 --png sheet.png   # look at it

# 3. train (smoke: 100 steps; full: 1500)
train/run_train.sh ~/.cache/artgen/loras/lgwoman1 1500       # checkpoints every 500 steps

# 4. use: models.json has "lgwoman1" (trigger lgwoman1 is prepended automatically, default scale 0.8)
.venv/bin/python artgen.py generate --backend sdxl --opt model=wai_v17 --opt loras=lgwoman1:0.8 \
    --prompt "1girl, solo, adult, red dress, standing, smile, cowboy shot" --width 640 --height 960 --seed 7 --out out/lg
# stack with the pixel LoRA: --opt loras=lgwoman1:0.8,pixel_art_xl:0.8 and add "anime style pixel art" to the prompt

# 5. evaluate
.venv/bin/python train/eval_lora.py --out OUT_DIR
```

## Dataset notes
- Generation failed to honour "portrait" / "upper body" with a full-body ref (FLUX returns full body), so close-ups are
  cropped from the full-body images (`make_dataset.py` CROPS, NEAREST upscale) and captions state the framing that is really in the image.
  8 images were dropped (chair/stool drawn behind the figure instead of sitting, duplicates). 26 kept: 20 full body + 6 crops.
- Square 1024 px (the trainer centre-crops to a square, which would cut standing figures), trained at 512.
- Captions: `lgwoman1, 1girl, adult, solo, <outfit>, <pose>, <framing>, simple background, <colour> background, pixel art`.
  Face and hair are not tagged. `pixel art` is tagged so the S3 look attaches to that tag, not to the trigger.
- Trigger token: **`lgwoman1`**. Clothed adults only; no nudity anywhere.

## Measured (M-series, 24 GB, fp32, rank 16, batch 1, 512 px, gradient checkpointing, AdamW lr 1e-4 constant, seed 42)
| Run | Time | Memory (MPS driver) |
|---|---|---|
| 100-step smoke test | 207 s (2.08 s/it incl. first-epoch VAE encoding; about 1.8 s/it steady) | peak 15.9 GB |
| 1500 steps | 59 min 7 s (2.37 s/it average; slower while the GPU was shared) | peak 14.9 GB |
| 30 eval images WAI v17 640x960 28 steps | about 40 s each | n/a |
LoRA file: 93 MB (fp32). Final loss is noisy (0.02 to 0.12), so judge by images, not loss.

## Evaluation (seed 7, WAI v17, columns: no LoRA | final 0.6 | 0.8 | 1.0 | step 500 @0.8 | step 1000 @0.8)
- Hair (auburn ponytail, brown eyes) and a consistent face type carry over in new scenes (sofa, kitchen, red dress, walking, pixel-stacked).
  Without the LoRA the same prompts give different people (black hair, blue eyes).
- 0.6 is partial (loose hair in some images), 0.8 to 1.0 is reliable. Step 500 already has the hair; 1000 and 1500 look alike. 1000 steps is enough.
- Style: the output keeps WAI's own look (it does not turn flat like the dataset), so `pixel_art_xl` stacks without trouble.
- Weak spots: identity is "same type of woman" rather than the exact face; poses are bent towards the dataset (hands clasped, front on),
  and walking-side views sometimes show black hair at 0.6.
