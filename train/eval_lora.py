#!/usr/bin/env python
"""Evaluate the lgwoman1 LoRA: prompts x (no LoRA | final 0.6/0.8/1.0 | step 500 / 1000 at 0.8) on WAI v17.

  .venv/bin/python train/eval_lora.py --out OUT_DIR [--w 640 --h 960 --seed 7]
Writes OUT_DIR/<prompt>_<cfg>.png and OUT_DIR/sheet.png (dataset samples on top, LoRA grid below).
Checkpoints are read from ~/.cache/artgen/loras/lgwoman1/checkpoint-<N>/ (copied once to uniquely named files).
"""
import argparse, shutil, sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artgen import get_backend, generate_images  # noqa: E402

L = Path.home() / ".cache/artgen/loras/lgwoman1"
DS = Path.home() / ".cache/artgen/datasets/lgwoman1"
PROMPTS = {
    "sofa": "1girl, solo, adult, sitting on a sofa, living room, indoors, blue sweater, jeans, full body",
    "kitchen": "1girl, solo, adult, standing in a kitchen, cooking, white apron, white t-shirt, kitchen background, cowboy shot",
    "reddress": "1girl, solo, adult, red dress, standing, smile, cowboy shot",
    "walk": "1girl, solo, adult, walking, from side, profile, green jacket, black pants, street, full body",
    "stack": "1girl, solo, adult, sitting on a sofa, living room, blue sweater, jeans, full body, anime style pixel art, thick dark outlines",
}
CFGS = [("none", None, None), ("fin0.6", "final", 0.6), ("fin0.8", "final", 0.8), ("fin1.0", "final", 1.0),
        ("s500@0.8", "500", 0.8), ("s1000@0.8", "1000", 0.8)]


def lora_file(which):
    if which == "final":
        return L / "pytorch_lora_weights.safetensors"
    dst = L / f"lgwoman1_step{which}.safetensors"
    if not dst.exists():
        shutil.copy(L / f"checkpoint-{which}" / "pytorch_lora_weights.safetensors", dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--w", type=int, default=640); ap.add_argument("--h", type=int, default=960)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    b = get_backend("sdxl"); b.load(model="wai_v17")
    for pk, tags in PROMPTS.items():
        for cn, which, sc in CFGS:
            f = out / f"{pk}_{cn}.png"
            if f.exists():
                continue
            loras = []
            if which:
                loras.append(f"{lora_file(which)}:{sc}")
            if pk == "stack":
                loras.append("pixel_art_xl:0.8")
            prompt = ("lgwoman1, " if which else "") + tags
            opts = {"model": "wai_v17", "background": "simple background"}
            if loras:
                opts["loras"] = ",".join(loras)
            generate_images(b, prompt, raw_prompt=False, seed=a.seed, n=1, width=a.w, height=a.h, negative=None,
                            opts=opts, out_dir=out, stem=f"{pk}_{cn}")
            Path(out / f"{pk}_{cn}_s{a.seed}.png").rename(f)
            Path(out / f"{pk}_{cn}_s{a.seed}.json").rename(out / f"{pk}_{cn}.json")
            print(f.name, flush=True)
    # sheet
    t_w, t_h = 320, 480
    cols = len(CFGS)
    ds = ["01", "04", "08", "13", "19", "28"]
    top = Image.new("RGB", (cols * t_w, 200 + 14), "white")
    for i, d in enumerate(ds):
        im = Image.open(DS / f"{d}.png").resize((200, 200), Image.LANCZOS); top.paste(im, (i * 210, 14))
    ImageDraw.Draw(top).text((3, 1), "dataset samples (FLUX klein + ref, S3 pixel)", fill="black")
    sheet = Image.new("RGB", (cols * t_w, 214 + len(PROMPTS) * (t_h + 14) + 14), "white")
    sheet.paste(top, (0, 0)); dr = ImageDraw.Draw(sheet)
    for ci, (cn, _, _) in enumerate(CFGS):
        dr.text((ci * t_w + 3, 214), cn, fill="black")
    for ri, pk in enumerate(PROMPTS):
        y = 228 + ri * (t_h + 14)
        dr.text((3, y), pk, fill="black")
        for ci, (cn, _, _) in enumerate(CFGS):
            im = Image.open(out / f"{pk}_{cn}.png").resize((t_w, t_h), Image.LANCZOS)
            sheet.paste(im, (ci * t_w, y + 14))
    sheet.save(out / "sheet.png"); print(out / "sheet.png")


if __name__ == "__main__":
    main()
