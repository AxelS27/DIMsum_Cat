"""Upscale all dimsum_cat sprite frames 4x using Real-ESRGAN anime model.

Run once:  python scripts/upscale_sprites.py
- Already-HD frames (target size ~4x original) are skipped.
- Oversized frames (upscaled more than 4x) are downscaled to target first.
- src/models.py SPRITE_UPSCALE is set to 1 when done.
"""
from __future__ import annotations

import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from PIL import Image
from realesrgan import RealESRGANer

ROOT        = Path(__file__).resolve().parent.parent
ANIM_DIR    = ROOT / "assets" / "sprites" / "dimsum_cat" / "animations"
WEIGHTS_DIR = ROOT / "assets" / "sprites" / "dimsum_cat" / ".esrgan_weights"
MODEL_PATH  = WEIGHTS_DIR / "RealESRGAN_x4plus_anime_6B.pth"
MODEL_URL   = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/"
    "v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"
)
FRAME_NAMES = ("frame_a.png", "frame_b.png", "frame_c.png", "frame_d.png")
MODELS_PY   = ROOT / "src" / "models.py"

# Original frames are ~148-176 x 113-128 px.
# Target after 4x upscale: ~592-704 x 452-512 px.
# Anything >= 500px wide is "already HD" (correct 4x).
# Anything >= 1000px wide is "oversized" (was upscaled more than once).
HD_THRESHOLD       = 500   # px: skip if width >= this
OVERSIZE_THRESHOLD = 1000  # px: downscale to 4x target if width >= this
TARGET_SCALE       = 4


def download_weights() -> None:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        print(f"  Weights already present: {MODEL_PATH.name}")
        return
    print(f"  Downloading {MODEL_URL} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH,
        reporthook=lambda b, bs, total: print(
            f"    {min(b*bs, total)/total*100:.0f}%", end="\r", flush=True
        )
    )
    print(f"  Downloaded: {MODEL_PATH.name}")


def build_upsampler() -> RealESRGANer:
    model = RRDBNet(
        num_in_ch=3, num_out_ch=3, num_feat=64,
        num_block=6, num_grow_ch=32, scale=4,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return RealESRGANer(
        scale=4,
        model_path=str(MODEL_PATH),
        model=model,
        tile=0,
        tile_pad=10,
        pre_pad=0,
        half=torch.cuda.is_available(),
        device=device,
    )


def upscale_frame(upsampler: RealESRGANer, path: Path) -> tuple[int, int]:
    """Upscale one frame in-place. Returns (new_w, new_h)."""
    img   = Image.open(path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]
    bgr   = np.array(img.convert("RGB"))[:, :, ::-1]
    out_bgr, _ = upsampler.enhance(bgr, outscale=TARGET_SCALE)
    out_rgb = out_bgr[:, :, ::-1]
    out_img = Image.fromarray(out_rgb, "RGB")
    alpha_up = Image.fromarray(alpha).resize(
        (out_img.width, out_img.height), Image.Resampling.LANCZOS
    )
    out_img.putalpha(alpha_up)
    out_img.save(path, "PNG")
    return out_img.width, out_img.height


def fix_oversized_frame(path: Path) -> tuple[int, int]:
    """Downscale an oversized frame (upscaled >1x too many) to TARGET_SCALE x original."""
    img = Image.open(path).convert("RGBA")
    # Infer original by dividing by TARGET_SCALE*TARGET_SCALE (was upscaled twice)
    # Use exact division: width / TARGET_SCALE -> target width
    target_w = img.width  // TARGET_SCALE
    target_h = img.height // TARGET_SCALE
    out = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    out.save(path, "PNG")
    return target_w, target_h


def patch_sprite_upscale() -> None:
    """Set SPRITE_UPSCALE = 1 in src/models.py."""
    text     = MODELS_PY.read_text(encoding="utf-8")
    new_text = re.sub(r"(SPRITE_UPSCALE\s*=\s*)\d+", r"\g<1>1", text)
    if new_text == text:
        print("  SPRITE_UPSCALE already 1, skipping.")
        return
    MODELS_PY.write_text(new_text, encoding="utf-8")
    print("  Patched src/models.py: SPRITE_UPSCALE = 1")


def main() -> None:
    print("=== DIMsum Cat Sprite Upscaler ===\n")

    print("[1/3] Downloading model weights...")
    download_weights()

    print("\n[2/3] Building Real-ESRGAN upsampler (anime 6B, CPU)...")
    upsampler = build_upsampler()

    anim_dirs = sorted(p for p in ANIM_DIR.iterdir() if p.is_dir())
    total     = len(anim_dirs)
    print(f"\n[3/3] Processing {total} animations...\n")

    t_start    = time.time()
    done_count = 0

    for i, anim_path in enumerate(anim_dirs, 1):
        name       = anim_path.name
        first_path = anim_path / FRAME_NAMES[0]
        if not first_path.exists():
            print(f"  [{i:02d}/{total}] {name:<30} MISSING frame_a")
            continue

        w0, _ = Image.open(first_path).size

        if w0 >= OVERSIZE_THRESHOLD:
            # Oversized — was accidentally upscaled more than once; downscale back
            for fname in FRAME_NAMES:
                fp = anim_path / fname
                if fp.exists():
                    tw, th = fix_oversized_frame(fp)
            print(f"  [{i:02d}/{total}] {name:<30} FIXED  oversized -> {tw}x{th}")
            done_count += 1

        elif w0 >= HD_THRESHOLD:
            print(f"  [{i:02d}/{total}] {name:<30} SKIP   already HD ({w0}px wide)")

        else:
            t0 = time.time()
            nw = nh = 0
            for fname in FRAME_NAMES:
                fp = anim_path / fname
                if fp.exists():
                    nw, nh = upscale_frame(upsampler, fp)
            elapsed  = time.time() - t0
            done_count += 1
            remaining = total - i
            avg_t     = (time.time() - t_start) / done_count
            eta_s     = int(remaining * avg_t)
            eta_m     = eta_s // 60
            print(
                f"  [{i:02d}/{total}] {name:<30} OK     {nw}x{nh}"
                f"  ({elapsed:.0f}s, ETA ~{eta_m}m)"
            )
        sys.stdout.flush()

    print(f"\n[PATCH] Updating src/models.py...")
    patch_sprite_upscale()

    total_t = int(time.time() - t_start)
    print(f"\nDone in {total_t//60}m {total_t%60}s. All sprites are now HD.")
    print("SPRITE_UPSCALE = 1 — runtime loads files as-is (no extra upscaling).")


if __name__ == "__main__":
    main()
