"""
Extract animation frames from DIMsum Cat design sheets.

Each sheet is 1536x1024 with two pages side-by-side.
Each page has 6 animation rows × 4 frames (A-D).

Strategy:
  1. Split sheet into left/right pages.
  2. Extract each cell with generous margin.
  3. Remove background via BFS flood-fill from edges (handles light-pink bg).
  4. Find UNION content bounding box across all 4 frames of each animation.
  5. Add padding so nothing is ever cropped.
  6. Save all 4 frames at identical canvas size.
"""

from __future__ import annotations
from collections import deque
from pathlib import Path
import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Grid constants — measured precisely from per-row std brightness scan
# (consistent across all 1536×1024 design sheets in this pack)
# ---------------------------------------------------------------------------
SHEET_W, SHEET_H = 1536, 1024
PAGE_W  = SHEET_W // 2         # 768 px per page
N_ROWS  = 6
N_COLS  = 4

# Animation row boundaries (y) — from separator scan on design_2.png
ROW_TOPS = [135, 272, 412, 546, 672, 802]
ROW_BOTS = [263, 399, 532, 662, 791, 915]

# Column boundaries (x) within a single page
# Label column ends at x=115; 4 equal frame columns follow
LABEL_W = 115
COL_W   = (PAGE_W - LABEL_W) // N_COLS     # 163 px
COL_LEFTS  = [LABEL_W + c * COL_W          for c in range(N_COLS)]
COL_RIGHTS = [LABEL_W + (c + 1) * COL_W   for c in range(N_COLS)]

# Extra horizontal pixels grabbed beyond each column edge.
# Small enough to never bleed into adjacent columns (separator ~8px wide);
# large enough to capture effects that touch the cell boundary.
COL_MARGIN = 10

CONTENT_PAD  = 22              # transparent padding added around union bbox
BG_TOLERANCE = 38              # max channel diff for flood-fill bg removal


# ---------------------------------------------------------------------------
# Animation names — listed top-to-bottom for each page
# ---------------------------------------------------------------------------
ANIMATIONS: dict[str, list[tuple[str, list[str]]]] = {
    # design_2.png
    "design_2": [
        # (page_side, [row0_name, row1_name, ...])
        ("L", ["crying", "angry_pout", "sleepy_yawn",
               "shocked", "confused_thinking", "laughing_hard"]),
        ("R", ["embarrassed", "panic", "dizzy",
               "sick_fever", "determined", "mischief_grin"]),
    ],
    # design3.png
    "design3": [
        ("L", ["facepalm", "pleading", "proud",
               "nervous_sweat", "peekaboo", "cheering"]),
        ("R", ["hugging_pillow", "thumbs_up", "clapping",
               "salute", "need_a_hug", "sassy_pose"]),
    ],
    # design4.png
    "design4": [
        ("L", ["sulking", "begging", "sniffling",
               "startled_jump", "want_attention", "self_hug"]),
        ("R", ["side_eye", "tiny_tantrum", "cozy_blanket",
               "stretching", "tongue_out_tease", "happy_wiggle"]),
    ],
    # design5.png
    "design5": [
        ("L", ["head_tilt", "little_wave", "curious_peek",
               "daydreaming", "rubbing_eyes", "tiny_giggle"]),
        ("R", ["happy_bounce", "listening_closely", "tiny_stretch_sit",
               "blow_air_hmph", "peek_from_box", "mini_twirl"]),
    ],
}

FRAME_NAMES = ["frame_a", "frame_b", "frame_c", "frame_d"]


# ---------------------------------------------------------------------------
# Background removal via BFS flood-fill from all edges
# ---------------------------------------------------------------------------

def flood_fill_bg(rgb: np.ndarray, tolerance: int) -> np.ndarray:
    """Return a boolean mask — True where pixels are background.

    Seeds from all four canvas edges.  The fill propagates only through
    pixels whose max-channel distance to the seed colour is ≤ tolerance.
    This correctly handles the white cat body (enclosed by dark outlines)
    by never escaping through the outline, even though the body is similarly
    light to the background.
    """
    h, w = rgb.shape[:2]
    seed_color = _sample_seed(rgb)

    def is_bg(y: int, x: int) -> bool:
        return int(np.abs(rgb[y, x].astype(int) - seed_color).max()) <= tolerance

    visited = np.zeros((h, w), dtype=bool)
    mask    = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(y: int, x: int) -> None:
        if not visited[y, x] and is_bg(y, x):
            visited[y, x] = True
            queue.append((y, x))

    for x in range(w):
        enqueue(0, x); enqueue(h - 1, x)
    for y in range(h):
        enqueue(y, 0); enqueue(y, w - 1)

    while queue:
        y, x = queue.popleft()
        mask[y, x] = True
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                enqueue(ny, nx)

    return mask


def _sample_seed(rgb: np.ndarray) -> np.ndarray:
    """Average colour of the four 10×10 corner patches."""
    h, w = rgb.shape[:2]
    s = 10
    corners = [
        rgb[:s,  :s],
        rgb[:s,  w-s:],
        rgb[h-s:, :s],
        rgb[h-s:, w-s:],
    ]
    return np.stack([c.reshape(-1, 3) for c in corners]).mean(axis=(0, 1))


# ---------------------------------------------------------------------------
# Content bounding box
# ---------------------------------------------------------------------------

def content_bbox(alpha: np.ndarray) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1) of non-transparent pixels, or None if blank."""
    rows = np.any(alpha > 5, axis=1)
    cols = np.any(alpha > 5, axis=0)
    if not rows.any():
        return None
    r0, r1 = np.where(rows)[0][[0, -1]]
    c0, c1 = np.where(cols)[0][[0, -1]]
    return int(c0), int(r0), int(c1) + 1, int(r1) + 1


def union_bbox(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def remove_margin_artifacts(alpha: np.ndarray, margin: int) -> np.ndarray:
    """BFS connected-component sweep.

    Any cluster of non-transparent pixels that has zero pixels inside the
    central zone (i.e. every pixel is within `margin` of the left or right
    edge) is a side-bleed artifact from an adjacent cell and is cleared.

    Legitimate animation content (teardrops, Z's, confetti) is always
    connected to the character body which sits in the centre — so it always
    has at least one pixel in the centre zone and is preserved.
    """
    h, w = alpha.shape
    if margin <= 0 or w <= 2 * margin:
        return alpha

    binary  = alpha > 10
    visited = np.zeros((h, w), dtype=bool)
    result  = alpha.copy()

    for sy in range(h):
        for sx in range(w):
            if not binary[sy, sx] or visited[sy, sx]:
                continue
            pixels: list[tuple[int, int]] = []
            in_center = False
            q: deque[tuple[int, int]] = deque([(sy, sx)])
            visited[sy, sx] = True
            while q:
                y, x = q.popleft()
                pixels.append((y, x))
                if margin <= x < w - margin:
                    in_center = True
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < h and 0 <= nx < w
                            and not visited[ny, nx] and binary[ny, nx]):
                        visited[ny, nx] = True
                        q.append((ny, nx))
            if not in_center:
                for y, x in pixels:
                    result[y, x] = 0
    return result


def extract_animation(
    sheet: np.ndarray,
    page_x: int,
    row_idx: int,
    name: str,
    out_dir: Path,
) -> None:
    y0 = ROW_TOPS[row_idx]
    y1 = ROW_BOTS[row_idx]
    frames_rgba: list[np.ndarray] = []

    for col in range(N_COLS):
        true_left  = page_x + COL_LEFTS[col]
        true_right = page_x + COL_RIGHTS[col]

        # Grab COL_MARGIN extra pixels on each side so effects at the cell
        # boundary are captured; clamp so we never cross into label or next page.
        actual_x0 = max(page_x + LABEL_W,    true_left  - COL_MARGIN)
        actual_x1 = min(page_x + PAGE_W - 1, true_right + COL_MARGIN)

        # How many pixels we actually grabbed from adjacent cells
        left_grabbed  = true_left  - actual_x0   # pixels from left neighbour
        right_grabbed = actual_x1  - true_right  # pixels from right neighbour

        cell_rgb = sheet[y0:y1, actual_x0:actual_x1]
        bg_mask  = flood_fill_bg(cell_rgb, BG_TOLERANCE)
        alpha    = np.where(bg_mask, 0, 255).astype(np.uint8)

        # Step 1: Deterministically clear adjacent-cell zones.
        # We know exactly which pixels came from neighbours.
        cw = alpha.shape[1]
        if left_grabbed  > 0: alpha[:, :left_grabbed]       = 0
        if right_grabbed > 0: alpha[:, cw - right_grabbed:] = 0

        # Step 2: Remove isolated clusters that sit entirely within the outer
        # margin zone.  margin=24 covers the worst-case label text extension
        # (~22px for "Want Attention") while keeping cat body/effects that are
        # connected to the character in the centre of the frame.
        alpha = remove_margin_artifacts(alpha, margin=24)

        frames_rgba.append(np.dstack([cell_rgb, alpha]))

    # Union content bbox across all 4 frames
    boxes = [content_bbox(f[:, :, 3]) for f in frames_rgba]
    valid = [b for b in boxes if b is not None]

    if not valid:
        print(f"  WARNING: no content found for '{name}'")
        return

    ux0, uy0, ux1, uy1 = union_bbox(valid)

    # Pad, clamped to cell size
    cw, ch = frames_rgba[0].shape[1], frames_rgba[0].shape[0]
    ux0 = max(0,  ux0 - CONTENT_PAD)
    uy0 = max(0,  uy0 - CONTENT_PAD)
    ux1 = min(cw, ux1 + CONTENT_PAD)
    uy1 = min(ch, uy1 + CONTENT_PAD)

    anim_dir = out_dir / name
    anim_dir.mkdir(parents=True, exist_ok=True)

    for frame_rgba, fname in zip(frames_rgba, FRAME_NAMES):
        cropped = frame_rgba[uy0:uy1, ux0:ux1]
        Image.fromarray(cropped, "RGBA").save(anim_dir / f"{fname}.png")

    fw, fh = ux1 - ux0, uy1 - uy0
    print(f"  OK {name:30s}  {fw}x{fh} px")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ROOT is one level up from scripts/
    root       = Path(__file__).resolve().parent.parent
    design_dir = root / "assets" / "sprites" / "dimsum_cat" / "design"
    anim_dir   = root / "assets" / "sprites" / "dimsum_cat" / "animations"

    for sheet_stem, pages in ANIMATIONS.items():
        sheet_path = design_dir / f"{sheet_stem}.png"
        if not sheet_path.exists():
            print(f"SKIP (not found): {sheet_path}")
            continue

        print(f"\n=== {sheet_path.name} ===")
        sheet = np.array(Image.open(sheet_path).convert("RGB"))

        for side, names in pages:
            page_x = 0 if side == "L" else PAGE_W
            print(f"  -- {'left' if side=='L' else 'right'} page --")
            for row_idx, name in enumerate(names):
                extract_animation(sheet, page_x, row_idx, name, anim_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
