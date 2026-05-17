from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root — one level up from src/
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TTS_VOICE_DEFAULT          = "ko-KR-SunHiNeural"   # edge-tts female Korean voice

SPRITES_ROOT     = ROOT / "sprites"
ANIMATIONS_ROOT  = SPRITES_ROOT / "dimsum_cat" / "animations"
WATERMARK_PNG    = SPRITES_ROOT / "watermark.png"
CONTENT_ROOT     = ROOT / "content"
FRAME_NAMES      = ("frame_a.png", "frame_b.png", "frame_c.png", "frame_d.png")

# Base sprite frame hold — actual timing varies per frame for hand-animated feel
SPRITE_FRAME_MS = 220

# Padding added to each sprite (in original pixels) before upscaling.
# Gives side/top effects (burst lines, speech bubbles, cherry) breathing room.
SPRITE_PAD = 22

# Pre-upscale factor applied once at load time.
# Means per-frame resize is a downscale → sharp, not blurry.
SPRITE_UPSCALE = 4

# Named character anchor positions as (cx, cy) fractions of canvas.
# cy=0.60 puts the character center at 60% from top — visually centred on
# a vertical phone screen with text above and breathing room below.
POSITIONS: dict[str, tuple[float, float]] = {
    "center":      (0.50, 0.54),
    "center-high": (0.50, 0.44),
    "center-low":  (0.50, 0.64),
    "left":        (0.30, 0.54),
    "right":       (0.70, 0.54),
    "left-low":    (0.30, 0.64),
    "right-low":   (0.70, 0.64),
    "left-high":   (0.28, 0.44),
    "right-high":  (0.72, 0.44),
}

# (main_font_px, sub_font_px) at 720w canvas
TEXT_SIZES: dict[str, tuple[int, int]] = {
    "small":  (34, 22),
    "normal": (50, 30),
    "big":    (70, 38),
    "huge":   (92, 46),
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class StoryBeat:
    """One moment in the video story."""
    time: float            # seconds from start
    text: str              # main text (large, prominent)
    sub: str = ""          # secondary line — pinyin, translation, reaction
    animation: str = ""    # switch to this animation (empty = keep previous)
    pos: str = "center"    # named position or "cx,cy" e.g. "0.3,0.7"
    scale: float = 1.0     # character scale multiplier
    text_size: str = "normal"  # small | normal | big | huge
    tts_speed: float | None = None        # override auto-detected speed
    tts_temperature: float | None = None  # override auto-detected temperature


@dataclass
class RenderConfig:
    beats: list[StoryBeat]
    default_animation: str
    output_name: str
    duration: float
    fps: int
    width: int
    height: int
    bg: str
    watermark: str
    story_dir:          Path | None = None   # folder containing story.json; output goes here
    title:              str  = ""            # video title (embedded in MP4 + IG caption)
    description:        str  = ""           # IG description / caption
    save_gif:           bool = False
    tts:                bool = False
    tts_provider:       str  = "edge"                    # "edge" | "gpt_sovits"
    tts_voice:          str  = TTS_VOICE_DEFAULT          # edge-tts voice name
    gpt_sovits_server:  str  = "http://127.0.0.1:9880"   # local GPT-SoVITS API server
    gpt_sovits_ref:     str  = ""                         # reference audio path for voice cloning
    gpt_sovits_speed:   float = 0.88
    bg_music:           str  = ""
