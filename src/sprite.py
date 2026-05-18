from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from src.models import (
    ANIMATIONS_ROOT,
    FRAME_NAMES,
    SPRITE_FRAME_MS,
    SPRITE_PAD,
    SPRITE_UPSCALE,
)
from src.utils import list_animations


# ---------------------------------------------------------------------------
# Organic motion — layered sines at irrational frequency ratios so the motion
# never perfectly repeats and feels hand-drawn rather than mechanical.
# ---------------------------------------------------------------------------

def organic(t: float, freq: float = 1.0, phase: float = 0.0) -> float:
    """Multi-layer sine noise. Returns roughly in [-1, 1]."""
    return (
        0.50 * math.sin(t * freq * 1.000 + phase) +
        0.25 * math.sin(t * freq * 2.137 + phase * 1.7) +
        0.15 * math.sin(t * freq * 3.841 + phase * 0.9) +
        0.10 * math.sin(t * freq * 7.293 + phase * 2.3)
    )


def make_sprite_schedule(total_frames: int, fps: int, sprite_count: int) -> list[int]:
    """Pre-compute which sprite frame to show at each video frame.

    Holds each sprite frame for a slightly irregular duration so the animation
    feels hand-timed rather than metronomic.
    """
    base_hold = max(2, round(SPRITE_FRAME_MS / 1000 * fps))
    schedule: list[int] = []
    sprite_i = 0
    hold_count = 0
    current_hold = base_hold
    for _ in range(total_frames):
        schedule.append(sprite_i % sprite_count)
        hold_count += 1
        if hold_count >= current_hold:
            sprite_i += 1
            hold_count = 0
            # Vary next hold by ±1 frame — tiny randomness, big feel difference
            variation = round(organic(sprite_i * 0.61803, freq=1.0) * 1.2)
            current_hold = max(2, base_hold + variation)
    return schedule


def _repair_clipped_edges(img: Image.Image, check_px: int = 3, smear_px: int = 18) -> Image.Image:
    """Extend edges where opaque content sits at the canvas boundary.

    The sprite pack was exported with some content clipped at canvas edges
    (cherry top in normal_talk, speech bubble right in waiting_reply, etc.).
    For each clipped edge we mirror-smear the boundary pixels outward with a
    linear alpha fade — a cheap approximation of the missing round shapes.
    """
    import numpy as np

    arr   = np.array(img, dtype=np.uint8)
    alpha = arr[:, :, 3]
    h, w  = alpha.shape
    THR   = 20   # alpha threshold to consider "opaque"

    # Only repair LEFT and RIGHT edges — side effects (speech bubbles, burst
    # lines) smear cleanly because they're consistent outlines/curves.
    # TOP edge is NOT smeared: mirroring it causes a visible ghost image of
    # the dimsum shape above the cherry. The cherry tip being 1-2px cut at
    # source is far less noticeable than a mirror artifact at video size.
    # Bottom edge is left alone (cat body at baseline is intentional).
    right_clip = bool((alpha[:,  -check_px:] > THR).any())
    left_clip  = bool((alpha[:,  :check_px ] > THR).any())

    if not (right_clip or left_clip):
        return img   # nothing to repair

    er = smear_px if right_clip else 0
    el = smear_px if left_clip  else 0

    new_w = w + el + er
    out   = np.zeros((h, new_w, 4), dtype=np.uint8)

    # Place original
    out[:, el:el + w] = arr

    # Smear right: mirror cols rightward with decreasing alpha
    if right_clip:
        for i in range(er):
            src_x = w - 1 - min(i, w - 1)
            dst_x = el + w + i
            col   = arr[:, src_x].copy()
            fade  = max(0.0, 1.0 - (i + 1) / er)
            col[:, 3] = (col[:, 3] * fade).astype(np.uint8)
            out[:, dst_x] = col

    # Smear left: mirror cols leftward with decreasing alpha
    if left_clip:
        for i in range(el):
            src_x = min(i, w - 1)
            dst_x = el - 1 - i
            col   = arr[:, src_x].copy()
            fade  = max(0.0, 1.0 - (i + 1) / el)
            col[:, 3] = (col[:, 3] * fade).astype(np.uint8)
            out[:, dst_x] = col

    return Image.fromarray(out, "RGBA")


def load_frames(animation: str, character: str = "") -> tuple[list[Image.Image], tuple[int, int]]:
    """Load sprite frames, repair clipped edges, pad, and pre-upscale once.

    Returns (upscaled_frames, original_size_before_any_processing).
    Pre-upscaling means per-frame work is mostly a downscale → sharp output.
    """
    from src.models import SPRITES_ROOT
    anim_dir = (SPRITES_ROOT / character / "animations" / animation) if character else (ANIMATIONS_ROOT / animation)
    if not anim_dir.exists():
        available = ", ".join(list_animations()) or "none"
        raise FileNotFoundError(f"Animation '{animation}' not found for character '{character or 'dimsum_cat'}'. Available: {available}")
    frames = []
    for name in FRAME_NAMES:
        p = anim_dir / name
        if not p.exists():
            raise FileNotFoundError(f"Missing: {p}")
        frames.append(Image.open(p).convert("RGBA"))
    sizes = {f.size for f in frames}
    if len(sizes) != 1:
        raise ValueError(f"'{animation}' frames have inconsistent sizes: {sorted(sizes)}")

    orig_size: tuple[int, int] = frames[0].size   # original canvas size

    processed: list[Image.Image] = []
    for frame in frames:
        # Add uniform padding so rendering never clips side effects
        padded = Image.new("RGBA",
                           (frame.width  + 2 * SPRITE_PAD,
                            frame.height + 2 * SPRITE_PAD),
                           (0, 0, 0, 0))
        padded.paste(frame, (SPRITE_PAD, SPRITE_PAD))

        # Pre-upscale once with LANCZOS — per-frame ops will mostly downscale
        up = padded.resize(
            (padded.width * SPRITE_UPSCALE, padded.height * SPRITE_UPSCALE),
            Image.Resampling.LANCZOS,
        )
        processed.append(up)

    return processed, orig_size
