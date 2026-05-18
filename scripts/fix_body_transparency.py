"""Fix transparent white body holes in all dimsum_cat sprite frames.

White body areas of the cat become transparent when the background is removed,
since both the background and the cat's white fur are the same color. This script
grows outward from opaque pixels into adjacent white-transparent pixels and fills
them with opaque white.

Run: python scripts/fix_body_transparency.py
"""
from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

ROOT     = Path(__file__).resolve().parent.parent
ANIM_DIR = ROOT / "assets" / "sprites" / "dimsum_cat" / "animations"
FRAMES   = ("frame_a.png", "frame_b.png", "frame_c.png", "frame_d.png")


def fix_frame(fp: Path) -> int:
    """Fill transparent white body holes. Returns count of fixed pixels."""
    img  = Image.open(fp).convert("RGBA")
    arr  = np.array(img, dtype=np.uint8)
    alpha = arr[:, :, 3].astype(np.int32)
    rgb   = arr[:, :, :3].astype(np.int32)
    h, w  = alpha.shape

    opaque            = alpha > 30
    white_transparent = (
        (alpha < 30)
        & (rgb[:, :, 0] > 180)
        & (rgb[:, :, 1] > 180)
        & (rgb[:, :, 2] > 180)
    )

    visited   = opaque.copy()
    fill_mask = np.zeros((h, w), dtype=bool)
    q         = deque()

    # Seed: opaque pixels that border a white-transparent pixel
    oys, oxs = np.where(opaque)
    for y, x in zip(oys.tolist(), oxs.tolist()):
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if (
                0 <= ny < h and 0 <= nx < w
                and white_transparent[ny, nx]
                and not visited[ny, nx]
            ):
                visited[ny, nx]   = True
                fill_mask[ny, nx] = True
                q.append((ny, nx))

    # Grow through connected white-transparent region
    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if (
                0 <= ny < h and 0 <= nx < w
                and white_transparent[ny, nx]
                and not visited[ny, nx]
            ):
                visited[ny, nx]   = True
                fill_mask[ny, nx] = True
                q.append((ny, nx))

    n = int(fill_mask.sum())
    if n > 0:
        out               = arr.copy()
        out[fill_mask, 0] = 255
        out[fill_mask, 1] = 255
        out[fill_mask, 2] = 255
        out[fill_mask, 3] = 255
        Image.fromarray(out, "RGBA").save(str(fp), "PNG")
    return n


def main() -> None:
    anims = sorted(p for p in ANIM_DIR.iterdir() if p.is_dir())
    total = len(anims)
    t0    = time.time()

    print(f"Fixing transparent body holes in {total} animations...\n")

    for i, anim in enumerate(anims, 1):
        total_px  = 0
        had_error = False
        for fname in FRAMES:
            fp = anim / fname
            if not fp.exists():
                continue
            try:
                total_px += fix_frame(fp)
            except Exception as e:
                print(f"  ERROR on {fp.name}: {e}")
                had_error = True

        if had_error:
            tag = "ERROR"
        elif total_px > 0:
            tag = f"FIXED {total_px:,}px"
        else:
            tag = "OK    (no holes)"

        print(f"  [{i:02d}/{total}] {anim.name:<30} {tag}")
        sys.stdout.flush()

    print(f"\nDone in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
