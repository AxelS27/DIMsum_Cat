"""
DIMsum Cat — Background Panel Splitter + Upscaler
Detects vertical dividers, crops each panel cleanly, upscales to 720x1280 (9:16).

Usage:
    python scripts/process_background.py royal_palace.png
    python scripts/process_background.py royal_palace.png --names kitchen dining_hall ramyeon_closeup
    python scripts/process_background.py royal_palace.png --preview
    python scripts/process_background.py royal_palace.png --no-upscale
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT          = Path(__file__).resolve().parent.parent
BG_DESIGN_DIR = ROOT / "assets" / "background" / "design"
BG_OUT_DIR    = ROOT / "assets" / "background"
MODEL_PATH    = ROOT / "assets" / "sprites" / "dimsum_cat" / ".esrgan_weights" / "RealESRGAN_x4plus_anime_6B.pth"

TARGET_W, TARGET_H = 720, 1280  # 9:16


# ─────────────────────────────────────────────────────────────────────────────
# Panel detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_panel_bounds(arr: np.ndarray, n_panels: int = 3) -> list[tuple[int, int]]:
    """
    Find (x_start, x_end) for each panel by locating vertical divider bands.
    Dividers are detected as columns that are consistently bright (white border)
    or consistently dark — whichever pattern dominates near the expected split.
    """
    h, w = arr.shape[:2]
    gray = arr[:, :, :3].mean(axis=2)         # (h, w) float
    col_mean = gray.mean(axis=0)              # (w,)  average brightness per column

    # Smooth slightly to avoid single-pixel noise
    kernel = np.ones(5) / 5
    col_smooth = np.convolve(col_mean, kernel, mode="same")

    expected_splits = [w * i // n_panels for i in range(1, n_panels)]
    search_radius   = max(40, w // (n_panels * 3))

    dividers: list[tuple[int, int]] = []   # (band_start, band_end)
    for exp_x in expected_splits:
        x0 = max(0, exp_x - search_radius)
        x1 = min(w, exp_x + search_radius)
        region = col_smooth[x0:x1]

        # Check if divider is bright (white border) or dark
        region_min = region.min()
        region_max = region.max()
        if region_max - col_smooth.mean() > col_smooth.mean() - region_min:
            # Bright divider
            peak_local = region.argmax()
        else:
            # Dark divider
            peak_local = region.argmin()

        peak_x = x0 + peak_local

        # Expand to full band width (≥3px consistent)
        threshold = (col_smooth[peak_x] + col_smooth.mean()) / 2
        if col_smooth[peak_x] > col_smooth.mean():
            in_band = lambda x: col_smooth[x] > threshold  # noqa: E731
        else:
            in_band = lambda x: col_smooth[x] < threshold  # noqa: E731

        band_start = peak_x
        while band_start > 0 and in_band(band_start - 1):
            band_start -= 1
        band_end = peak_x
        while band_end < w - 1 and in_band(band_end + 1):
            band_end += 1

        dividers.append((band_start, band_end))

    # Build panel bounds from dividers
    bounds: list[tuple[int, int]] = []
    prev = 0
    for band_start, band_end in dividers:
        bounds.append((prev, band_start))
        prev = band_end + 1
    bounds.append((prev, w))
    return bounds


# ─────────────────────────────────────────────────────────────────────────────
# Preview
# ─────────────────────────────────────────────────────────────────────────────

def save_preview(img: Image.Image, bounds: list[tuple[int, int]], design_path: Path) -> Path:
    out = img.copy().convert("RGB")
    draw = ImageDraw.Draw(out)
    colors = [(255, 50, 50), (50, 255, 50), (50, 50, 255)]
    for i, (x0, x1) in enumerate(bounds):
        c = colors[i % len(colors)]
        draw.rectangle([x0, 0, x1, img.height - 1], outline=c, width=3)
        draw.text((x0 + 8, 8), f"Panel {i+1}\n{x1-x0}px", fill=c)

    preview_dir = design_path.parent / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out_path = preview_dir / (design_path.stem + "_bg_preview.png")
    out.save(str(out_path))
    print(f"Preview saved: {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Upscale
# ─────────────────────────────────────────────────────────────────────────────

def build_upsampler():
    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                    num_block=6, num_grow_ch=32, scale=4)
    return RealESRGANer(scale=4, model_path=str(MODEL_PATH), model=model,
                        tile=0, tile_pad=10, pre_pad=0, half=torch.cuda.is_available(),
                        device=device)


def upscale_panel(up, panel: Image.Image) -> Image.Image:
    bgr = np.array(panel.convert("RGB"))[:, :, ::-1]
    out_bgr, _ = up.enhance(bgr, outscale=4)
    return Image.fromarray(out_bgr[:, :, ::-1], "RGB")


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def process(design_path: Path, names: list[str], out_dir: Path, use_upscale: bool) -> None:
    img = Image.open(design_path).convert("RGB")
    arr = np.array(img)

    print(f"\n[0] Detecting panels in {design_path.name}  ({img.width}x{img.height})")
    bounds = detect_panel_bounds(arr, n_panels=len(names))
    for i, (x0, x1) in enumerate(bounds):
        print(f"  Panel {i+1} ({names[i]}): x={x0}..{x1}  ({x1-x0}px wide)")

    save_preview(img, bounds, design_path)

    up = None
    if use_upscale:
        if not MODEL_PATH.exists():
            print(f"  WARNING: ESRGAN weights not found at {MODEL_PATH}")
            print("  Falling back to Lanczos resize.")
            use_upscale = False
        else:
            print(f"\n[1] Loading Real-ESRGAN (anime 6B)...")
            up = build_upsampler()

    print(f"\n[{'2' if use_upscale else '1'}] Processing panels -> {out_dir}")
    t0 = time.time()

    for i, (name, (x0, x1)) in enumerate(zip(names, bounds), 1):
        panel = img.crop((x0, 0, x1, img.height))

        if use_upscale:
            print(f"  [{i}/{len(names)}] {name}: upscaling 4x...", end=" ", flush=True)
            t1 = time.time()
            panel = upscale_panel(up, panel)
            print(f"{panel.width}x{panel.height}  ({time.time()-t1:.0f}s)", end=" -> ")

        # Final resize to exact 9:16
        panel = panel.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS)
        out_path = out_dir / f"{name}.png"
        panel.save(str(out_path), "PNG")
        print(f"saved {TARGET_W}x{TARGET_H}  {out_path.name}")

    print(f"\nDone in {time.time()-t0:.1f}s  ->  {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python scripts/process_background.py",
        description="Split 3-panel background image into individual 9:16 panels.",
    )
    parser.add_argument("design", help="Background design PNG (e.g. royal_palace.png)")
    parser.add_argument("--names", nargs="+",
                        default=["panel_1", "panel_2", "panel_3"],
                        help="Names for each panel (left to right)")
    parser.add_argument("--out", default=None, help="Output directory")
    parser.add_argument("--preview", action="store_true",
                        help="Save grid preview only, don't process")
    parser.add_argument("--no-upscale", action="store_true",
                        help="Skip ESRGAN upscale, use Lanczos resize only")
    args = parser.parse_args()

    design_path = Path(args.design)
    if not design_path.exists():
        design_path = BG_DESIGN_DIR / args.design
    if not design_path.exists():
        sys.exit(f"ERROR: file not found: {args.design}")

    out_dir = Path(args.out) if args.out else BG_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.preview:
        img  = Image.open(design_path).convert("RGB")
        bounds = detect_panel_bounds(np.array(img), n_panels=len(args.names))
        save_preview(img, bounds, design_path)
        return

    process(design_path, args.names, out_dir, use_upscale=not args.no_upscale)


if __name__ == "__main__":
    main()
