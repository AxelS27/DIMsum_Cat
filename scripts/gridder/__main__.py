"""
DIMsum Cat — Sprite Sheet Gridder
Crop → Upscale → Remove BG, fully automatic from any design PNG.

Usage:
    python scripts/gridder design_1.png
    python scripts/gridder design_1.png --step 1          # crop only
    python scripts/gridder design_1.png --step 2          # upscale only
    python scripts/gridder design_1.png --step 3          # remove bg only
    python scripts/gridder design_1.png --out my/folder   # custom output dir
    python scripts/gridder design_1.png --preview         # show detected grid, no save

Config files: scripts/gridder/configs/<design_name>.json
  {
    "panels": [
      ["anim_name", ...],   <- left panel, top to bottom
      ["anim_name", ...]    <- right panel, top to bottom
    ]
  }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent.parent
GRIDDER_DIR = Path(__file__).resolve().parent
CONFIGS_DIR = GRIDDER_DIR / "configs"
MODEL_PATH  = ROOT / "assets/sprites/dimsum_cat/.esrgan_weights/RealESRGAN_x4plus_anime_6B.pth"
FRAME_NAMES = ("frame_a.png", "frame_b.png", "frame_c.png", "frame_d.png")


# ─────────────────────────────────────────────────────────────────────────────
# Grid detection
# ─────────────────────────────────────────────────────────────────────────────

def _is_green(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
    return (r < 100) & (g > 150) & (b < 100)


def detect_rows(arr: np.ndarray) -> tuple[int, int, list[tuple[int,int]]]:
    """Return (top_y, bot_y, [(sep_start, sep_end), ...])."""
    h, w = arr.shape[:2]
    green = _is_green(arr)
    scan_xs = [x for x in [100,200,300,400,500,600,900,1000,1100,1200,1300,1400] if x < w]
    N = len(scan_xs)

    scores = np.zeros(h, dtype=int)
    for sx in scan_xs:
        scores += (~green[:, sx]).astype(int)

    bands: list[tuple[int,int]] = []
    in_b = False
    for y in range(h):
        if scores[y] == N:
            if not in_b: start = y; in_b = True
        else:
            if in_b and (y - start) >= 3: bands.append((start, y - 1))
            in_b = False
    if in_b and (h - 1 - start) >= 3: bands.append((start, h - 1))

    header = bands[0] if bands and bands[0][0] == 0 else None
    bottom = bands[-1] if bands and bands[-1][1] >= h - 30 else None
    mid    = [b for b in bands if b is not header and b is not bottom]

    top_y = (header[1] + 1) if header else 0
    bot_y = (bottom[0] - 1) if bottom else h - 1
    return top_y, bot_y, mid


def detect_cols(arr: np.ndarray, cell_rows: list[tuple[int,int]]) -> list[tuple[int,int,int]]:
    """Return [(start, end, center), ...] for each column separator band.

    True cell borders are light-colored (white/pink design border).
    Cat body center outlines are DARK (black). We reject dark bands.
    """
    h, w = arr.shape[:2]
    green = _is_green(arr)
    all_ys = np.concatenate([np.arange(y0, y1 + 1) for y0, y1 in cell_rows])
    frac = (~green[np.ix_(all_ys, np.arange(w))]).mean(axis=0)
    is_border = frac > 0.85

    bands: list[tuple[int,int]] = []
    in_b = False
    for x in range(w):
        if is_border[x]:
            if not in_b: start = x; in_b = True
        else:
            if in_b and (x - start) >= 2: bands.append((start, x - 1))
            in_b = False

    # Keep only narrow bands (true borders ≤16px; cat-body blobs are wider)
    narrow = [(s, e) for s, e in bands if e - s + 1 <= 16]

    # Position check: a true cell border is non-green at the very TOP of
    # EACH cell row (the border runs the full height across all rows).
    # Cat bodies start a few pixels below the cell top, so topmost pixels
    # in most rows will be GREEN for false-positive cat-body columns.
    # Check top 6px of every cell row — if non-green in ≥50% of rows → true separator.
    TOP_PX  = 6
    result  = []
    for s, e in narrow:
        cx = (s + e) // 2
        rows_with_border = 0
        for y0, y1 in cell_rows:
            top_ys = range(y0, min(y0 + TOP_PX, y1))
            non_green = sum(1 for y in top_ys if not green[y, cx])
            if non_green >= len(top_ys) * 0.6:
                rows_with_border += 1
        if rows_with_border >= len(cell_rows) * 0.5:   # border in ≥50% of rows = true sep
            result.append((s, e, cx))
    return result


def build_grid(arr: np.ndarray):
    """Return (cell_rows, left_bands, right_bands, outer_border_w)."""
    h, w = arr.shape[:2]
    top_y, bot_y, mid_bands = detect_rows(arr)

    row_starts = [top_y]      + [e + 1 for s, e in mid_bands]
    row_ends   = [e for s, e in mid_bands] + [bot_y]
    cell_rows  = list(zip(row_starts, row_ends))

    col_bands = detect_cols(arr, cell_rows)
    mid_x     = w // 2
    div_idx   = min(range(len(col_bands)), key=lambda i: abs(col_bands[i][2] - mid_x))

    left_bands  = col_bands[:div_idx + 1]
    right_bands = col_bands[div_idx:]
    outer_w     = col_bands[0][1] + 1

    return cell_rows, left_bands, right_bands, outer_w


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Crop
# ─────────────────────────────────────────────────────────────────────────────

def step_crop(design_path: Path, out_dir: Path, panels: list[list[str]],
              wide_cols: list[int] | None = None) -> None:
    print(f"\n[1/3] Crop — {design_path.name}")
    img = Image.open(design_path).convert("RGBA")
    arr = np.array(img)
    h, w = arr.shape[:2]

    cell_rows, left_bands, right_bands, outer_w = build_grid(arr)
    print(f"  Rows ({len(cell_rows)}): {cell_rows}")

    def crop_panel(bands, names):
        frame_bands = bands[1:]
        for row_i, (y0, y1) in enumerate(cell_rows):
            if row_i >= len(names): break
            anim_dir = out_dir / names[row_i]
            anim_dir.mkdir(parents=True, exist_ok=True)
            for col_i, fname in enumerate(FRAME_NAMES):
                if col_i >= len(frame_bands): break
                x0 = frame_bands[col_i][1] + 1
                x1 = (frame_bands[col_i+1][0] - 1) if col_i+1 < len(frame_bands) else (w - 1 - outer_w)
                x0, x1 = max(0, x0), min(w, x1)
                img.crop((x0, max(0,y0), x1, min(h,y1))).save(str(anim_dir / fname), "PNG")
            print(f"  {names[row_i]:<26} {y1-y0+1}px tall")

    if wide_cols is not None:
        # Single-panel mode: all 4 frames span the full sheet width.
        # wide_cols = explicit list of separator center-x values (all cols, no L/R split).
        print(f"  Wide-cols mode: {wide_cols}")
        all_bands = [(x - 3, x + 3, x) for x in wide_cols]
        outer_w   = wide_cols[0] + 4
        crop_panel(all_bands, panels[0])
    else:
        print(f"  L-seps: {[c for s,e,c in left_bands]}  R-seps: {[c for s,e,c in right_bands]}")
        crop_panel(left_bands,  panels[0])
        if len(panels) > 1:
            crop_panel(right_bands, panels[1])
    print("  Done.")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Upscale 4x (with BG intact for clean edges)
# ─────────────────────────────────────────────────────────────────────────────

def _build_upsampler():
    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                    num_block=6, num_grow_ch=32, scale=4)
    return RealESRGANer(scale=4, model_path=str(MODEL_PATH), model=model,
                        tile=0, tile_pad=10, pre_pad=0, half=torch.cuda.is_available(),
                        device=device)


def _upscale_one(up, fp: Path) -> tuple[int,int]:
    img = Image.open(fp).convert("RGB")
    bgr = np.array(img)[:,:,::-1]
    out_bgr, _ = up.enhance(bgr, outscale=4)
    out = Image.fromarray(out_bgr[:,:,::-1], "RGB")
    tmp = str(fp) + ".tmp.png"
    out.save(tmp, "PNG"); os.replace(tmp, str(fp))
    return out.width, out.height


def step_upscale(out_dir: Path, panels: list[list[str]]) -> None:
    import torch
    device_label = "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
    print(f"\n[2/3] Upscale 4x — Real-ESRGAN anime model ({device_label})")
    if not MODEL_PATH.exists():
        sys.exit(f"  ERROR: weights not found at {MODEL_PATH}")

    up = _build_upsampler()
    all_names = [n for panel in panels for n in panel]
    t0 = time.time()

    for i, name in enumerate(all_names, 1):
        anim_dir = out_dir / name
        t1 = time.time()
        nw = nh = 0
        for fname in FRAME_NAMES:
            fp = anim_dir / fname
            if not fp.exists(): continue
            if Image.open(fp).width >= 500: nw, nh = Image.open(fp).size; continue
            nw, nh = _upscale_one(up, fp)

        # Normalise all frames to same (max) size
        fps = [anim_dir/f for f in FRAME_NAMES if (anim_dir/f).exists()]
        if fps:
            sizes = [Image.open(fp).size for fp in fps]
            mw, mh = max(s[0] for s in sizes), max(s[1] for s in sizes)
            for fp in fps:
                img = Image.open(fp).convert("RGBA")
                if img.size != (mw, mh):
                    img = img.resize((mw, mh), Image.Resampling.LANCZOS)
                    tmp = str(fp)+".tmp.png"; img.save(tmp,"PNG"); os.replace(tmp, str(fp))
            nw, nh = mw, mh

        done = i; avg = (time.time()-t0)/done; eta = int((len(all_names)-done)*avg)//60
        print(f"  [{i:02d}/{len(all_names)}] {name:<26} {nw}x{nh}  ({time.time()-t1:.0f}s, ETA ~{eta}m)")
        sys.stdout.flush()

    print(f"  Done in {(time.time()-t0)/60:.1f}m.")


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Remove background
# ─────────────────────────────────────────────────────────────────────────────

def _remove_bg(img: Image.Image) -> tuple[Image.Image, int]:
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
    h, w = arr.shape[:2]

    # Pass 1: green pixels
    green = (g > r + 15) & (g > b + 15) & (g > 100)
    arr[green, 3] = 0
    n = int(green.sum())

    # Pass 2: white border — flood fill from edges
    alpha = arr[:,:,3].astype(int)
    white = (alpha > 0) & (r > 200) & (g > 200) & (b > 200)
    visited = np.zeros((h, w), dtype=bool)
    q = deque()
    for y in range(h):
        for x in [0, w-1]:
            if white[y,x] and not visited[y,x]: visited[y,x]=True; q.append((y,x))
    for x in range(w):
        for y in [0, h-1]:
            if white[y,x] and not visited[y,x]: visited[y,x]=True; q.append((y,x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
            ny, nx = y+dy, x+dx
            if 0<=ny<h and 0<=nx<w and not visited[ny,nx] and white[ny,nx]:
                visited[ny,nx]=True; q.append((ny,nx))
    arr[visited, 3] = 0
    n += int(visited.sum())

    # Pass 2.5: restore enclosed white areas (e.g. speech bubble interiors).
    # After edge flood fill, white pixels that were INSIDE closed outlines
    # (like speech bubbles) may have been incorrectly removed.
    # Grow outward from opaque pixels into adjacent white-transparent pixels
    # to restore them. The black outline acts as a boundary so this never
    # bleeds back into the actual background.
    alpha2   = arr[:,:,3].astype(int)
    r2,g2,b2 = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
    opaque   = alpha2 > 30
    wt       = (alpha2 < 30) & (r2 > 180) & (g2 > 180) & (b2 > 180)
    vis2     = opaque.copy()
    fill     = np.zeros((h, w), dtype=bool)
    q2       = deque()
    oys, oxs = np.where(opaque)
    for y, x in zip(oys.tolist(), oxs.tolist()):
        for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
            ny, nx = y+dy, x+dx
            if 0<=ny<h and 0<=nx<w and wt[ny,nx] and not vis2[ny,nx]:
                vis2[ny,nx]=True; fill[ny,nx]=True; q2.append((ny,nx))
    while q2:
        y, x = q2.popleft()
        for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
            ny, nx = y+dy, x+dx
            if 0<=ny<h and 0<=nx<w and wt[ny,nx] and not vis2[ny,nx]:
                vis2[ny,nx]=True; fill[ny,nx]=True; q2.append((ny,nx))
    if fill.any():
        arr[fill, 0] = 255; arr[fill, 1] = 255
        arr[fill, 2] = 255; arr[fill, 3] = 255


    # Pass 3: edge strip detection — density + run-length
    alpha2 = arr[:,:,3]
    DEPTH  = 14
    DENS   = 0.40

    for col in range(DEPTH):
        for x in [col, w-1-col]:
            ca = alpha2[:,x]
            if ca.astype(bool).sum() / h >= DENS:
                arr[:,x,3] = np.where(ca > 0, 0, ca)
    for row in range(DEPTH):
        for y in [row, h-1-row]:
            ra = alpha2[y,:]
            if ra.astype(bool).sum() / w >= DENS:
                arr[y,:,3] = np.where(ra > 0, 0, ra)

    def kill_runs(coords, dim_len):
        min_r = max(8, int(dim_len * 0.25))
        run = []
        for y, x in coords:
            if arr[y,x,3] > 0: run.append((y,x))
            else:
                if len(run) >= min_r:
                    for ry,rx in run: arr[ry,rx,3] = 0
                run = []
        if len(run) >= min_r:
            for ry,rx in run: arr[ry,rx,3] = 0

    for col in range(DEPTH):
        kill_runs([(y,col) for y in range(h)], h)
        kill_runs([(y,w-1-col) for y in range(h)], h)
    for row in range(DEPTH):
        kill_runs([(row,x) for x in range(w)], w)
        kill_runs([(h-1-row,x) for x in range(w)], w)

    # Pass 4: remove horizontal border lines — scan from bottom upward,
    # kill any row where visible pixels span > 70% of image width as a
    # single connected run (cell border remnant, not body content).
    alpha3 = arr[:,:,3]
    for y in range(h - 1, max(0, h - 60), -1):
        row_alpha = alpha3[y, :]
        visible_xs = np.where(row_alpha > 0)[0]
        if len(visible_xs) == 0:
            continue
        span = int(visible_xs[-1]) - int(visible_xs[0]) + 1
        if span > w * 0.70 and len(visible_xs) >= w * 0.60:
            arr[y, :, 3] = 0
            n += int((row_alpha > 0).sum())

    # Pass 4b: remove small isolated white pixel clusters (cell-border remnants).
    # Find connected components of pure-white visible pixels; remove any cluster
    # that is small (< 3% of image area) AND has no dark/colored neighbour.
    r4, g4, b4, a4 = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
    is_white  = (r4 > 200) & (g4 > 200) & (b4 > 200) & (a4 > 0)
    is_colored = a4 > 0 & ~is_white  # visible but not white
    # Label connected white components
    labeled = np.zeros((h, w), dtype=np.int32)
    comp_id  = 0
    comp_px  = {}
    for sy in range(h):
        for sx in range(w):
            if is_white[sy, sx] and labeled[sy, sx] == 0:
                comp_id += 1
                comp_px[comp_id] = []
                q = deque([(sy, sx)])
                labeled[sy, sx] = comp_id
                while q:
                    cy, cx = q.popleft()
                    comp_px[comp_id].append((cy, cx))
                    for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
                        ny, nx = cy+dy, cx+dx
                        if 0 <= ny < h and 0 <= nx < w and is_white[ny,nx] and labeled[ny,nx]==0:
                            labeled[ny,nx] = comp_id
                            q.append((ny, nx))
    max_small = int(h * w * 0.03)
    for cid, pixels in comp_px.items():
        if len(pixels) >= max_small:
            continue
        # Check if any neighbour of this cluster is a colored (non-white) pixel
        has_colored_neighbour = False
        for cy, cx in pixels:
            for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
                ny, nx = cy+dy, cx+dx
                if 0 <= ny < h and 0 <= nx < w and a4[ny,nx] > 0 and not is_white[ny,nx]:
                    has_colored_neighbour = True
                    break
            if has_colored_neighbour:
                break

        if not has_colored_neighbour:
            # Isolated white cluster — remove
            for cy, cx in pixels: arr[cy, cx, 3] = 0; n += 1
        else:
            # Has colored neighbours, but check fill ratio:
            # Nearly perfect rectangles (fill > 0.88) are cell-border artifacts
            pys = [p[0] for p in pixels]
            pxs = [p[1] for p in pixels]
            bbox_area = (max(pys)-min(pys)+1) * (max(pxs)-min(pxs)+1)
            fill_ratio = len(pixels) / bbox_area if bbox_area > 0 else 0
            if fill_ratio > 0.88 and len(pixels) < 2000:
                for cy, cx in pixels: arr[cy, cx, 3] = 0; n += 1

    # Pass 5: despill — remove white/light fringe pixels at character boundary.
    # ESRGAN anti-aliases against the white cell background, leaving semi-transparent
    # white halos. Kill any visible pixel where RGB is very bright (near-white) AND
    # it's adjacent to a transparent pixel (i.e., it's on the boundary).
    alpha5 = arr[:,:,3].astype(np.int32)
    r5, g5, b5 = arr[:,:,0].astype(np.int32), arr[:,:,1].astype(np.int32), arr[:,:,2].astype(np.int32)
    is_bright = (r5 > 220) & (g5 > 220) & (b5 > 220) & (alpha5 > 0)
    # A pixel is "on boundary" if any of its 4 neighbours is transparent
    pad_a = np.pad(alpha5, 1, constant_values=0)
    has_transp_neighbour = (
        (pad_a[:-2, 1:-1] == 0) | (pad_a[2:, 1:-1] == 0) |
        (pad_a[1:-1, :-2] == 0) | (pad_a[1:-1, 2:] == 0)
    )
    fringe = is_bright & has_transp_neighbour
    arr[fringe, 3] = 0
    n += int(fringe.sum())

    return Image.fromarray(arr, "RGBA"), n


def step_remove_bg(out_dir: Path, panels: list[list[str]]) -> None:
    print(f"\n[3/3] Remove background")
    for name in [n for panel in panels for n in panel]:
        anim_dir = out_dir / name
        total = 0
        for fname in FRAME_NAMES:
            fp = anim_dir / fname
            if not fp.exists(): continue
            fixed, n = _remove_bg(Image.open(fp))
            total += n
            tmp = str(fp)+".tmp.png"; fixed.save(tmp,"PNG"); os.replace(tmp, str(fp))
        print(f"  {name:<26} {total:,} px removed")
    print("  Done.")


# ─────────────────────────────────────────────────────────────────────────────
# Preview
# ─────────────────────────────────────────────────────────────────────────────

def preview_grid(design_path: Path) -> None:
    img = Image.open(design_path).convert("RGB")
    arr = np.array(img)
    cell_rows, left_bands, right_bands, _ = build_grid(arr)
    top_y, bot_y, mid_bands = detect_rows(arr)
    out  = img.copy()
    draw = ImageDraw.Draw(out)
    w    = img.width

    # Rows
    draw.line([(0,top_y),(w,top_y)], fill=(0,220,255), width=4)
    draw.line([(0,bot_y),(w,bot_y)], fill=(0,220,255), width=4)
    for s, e in mid_bands:
        draw.line([(0,(s+e)//2),(w,(s+e)//2)], fill=(255,220,0), width=4)

    # Cols
    for s, e, c in left_bands + right_bands:
        draw.line([(c,0),(c,img.height)], fill=(255,0,200), width=4)

    # Save to design_dir/preview/
    preview_dir = design_path.parent / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out_path = preview_dir / (design_path.stem + "_grid_preview.png")
    out.save(str(out_path))
    print(f"Preview saved: {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python scripts/gridder",
        description="Crop -> Upscale -> Remove BG from a sprite sheet design PNG.",
    )
    parser.add_argument("design", help="Design PNG filename (e.g. design_1.png)")
    parser.add_argument("--step", type=int, choices=[1,2,3],
                        help="Run only one step (1=crop, 2=upscale, 3=remove_bg)")
    parser.add_argument("--out", default=None,
                        help="Output directory (default: experiments/animations)")
    parser.add_argument("--preview", action="store_true",
                        help="Save grid overlay preview only, don't process")
    args = parser.parse_args()

    # Resolve design file — accept bare name or full path
    design_path = Path(args.design)
    if not design_path.exists():
        design_path = ROOT / "assets" / "sprites" / "dimsum_cat" / "design" / args.design
    if not design_path.exists():
        design_path = ROOT / "experiments" / "design" / args.design
    if not design_path.exists():
        sys.exit(f"ERROR: design file not found: {args.design}")

    # Load config
    cfg_path = CONFIGS_DIR / (design_path.stem + ".json")
    if not cfg_path.exists():
        sys.exit(f"ERROR: no config found at {cfg_path}\n"
                 f"Create it with: {{\"panels\": [[\"anim1\",...],[\"anim1\",...]] }}")
    cfg_data = json.loads(cfg_path.read_text())
    panels: list[list[str]] = cfg_data["panels"]
    wide_cols: list[int] | None = cfg_data.get("wide_cols")

    # Output dir
    out_dir = Path(args.out) if args.out else ROOT / "experiments" / "animations"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Design : {design_path}")
    print(f"Config : {cfg_path.name}  ({sum(len(p) for p in panels)} animations)")
    print(f"Output : {out_dir}")

    if args.preview:
        preview_grid(design_path); return

    # ── Rule: always generate preview first before any processing ────────────
    preview_dir = design_path.parent / "preview"
    print("\n[0/3] Generating grid preview...")
    preview_grid(design_path)
    print("      Review the preview above, then processing will begin.\n")

    steps = [args.step] if args.step else [1, 2, 3]
    t0    = time.time()

    if 1 in steps: step_crop(design_path, out_dir, panels, wide_cols=wide_cols)
    if 2 in steps: step_upscale(out_dir, panels)
    if 3 in steps: step_remove_bg(out_dir, panels)

    # ── Cleanup: delete preview folder after full pipeline (all 3 steps) ────
    if steps == [1, 2, 3] and preview_dir.exists():
        import shutil
        shutil.rmtree(preview_dir)
        print(f"Preview folder removed: {preview_dir}")

    print(f"\nAll done in {(time.time()-t0)/60:.1f}m  ->  {out_dir}")


if __name__ == "__main__":
    main()
