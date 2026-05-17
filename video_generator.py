from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Force UTF-8 output so Korean text doesn't crash on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TTS_VOICE_DEFAULT          = "ko-KR-SunHiNeural"   # edge-tts female Korean voice


ROOT = Path(__file__).resolve().parent
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
    story_dir: Path | None = None   # folder containing story.json; output goes here
    save_gif:           bool = False
    tts:                bool = False
    tts_provider:       str  = "edge"                    # "edge" | "gpt_sovits"
    tts_voice:          str  = TTS_VOICE_DEFAULT          # edge-tts voice name
    gpt_sovits_server:  str  = "http://127.0.0.1:9880"   # local GPT-SoVITS API server
    gpt_sovits_ref:     str  = ""                         # reference audio path for voice cloning
    gpt_sovits_speed:   float = 0.88
    bg_music:           str  = ""


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def find_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg  # type: ignore[import]
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass
    return shutil.which("ffmpeg")


def resolve_pos(pos: str) -> tuple[float, float]:
    if pos in POSITIONS:
        return POSITIONS[pos]
    try:
        a, b = pos.split(",")
        return float(a), float(b)
    except (ValueError, IndexError):
        return POSITIONS["center"]


LOCAL_FONTS_DIR = ROOT / "fonts"


def find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        # Jua — cute rounded Korean font downloaded to project/fonts/
        LOCAL_FONTS_DIR / "Jua-Regular.ttf",
        # System CJK fallbacks that actually contain Hangul glyphs
        Path("C:/Windows/Fonts/msjhbd.ttc") if bold else Path("C:/Windows/Fonts/msjh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/seguisb.ttf") if bold else Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


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


def measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    if not text:
        return 0, 0
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if measure(draw, text, font)[0] <= max_w:
        return [text]
    if " " not in text:                         # CJK: split by character
        lines, cur = [], ""
        for ch in text:
            if cur and measure(draw, cur + ch, font)[0] > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines
    words = text.split()                        # Latin: split by word
    lines, cur = [], ""
    for w in words:
        candidate = w if not cur else f"{cur} {w}"
        if cur and measure(draw, candidate, font)[0] > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    return lines


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_out_back(t: float) -> float:
    """Spring overshoot — punchy scale pop."""
    c1, c3 = 1.30, 2.30
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def list_animations() -> list[str]:
    if not ANIMATIONS_ROOT.exists():
        return []
    return sorted(p.name for p in ANIMATIONS_ROOT.iterdir() if p.is_dir())


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


def load_frames(animation: str) -> tuple[list[Image.Image], tuple[int, int]]:
    """Load sprite frames, repair clipped edges, pad, and pre-upscale once.

    Returns (upscaled_frames, original_size_before_any_processing).
    Pre-upscaling means per-frame work is mostly a downscale → sharp output.
    """
    anim_dir = ANIMATIONS_ROOT / animation
    if not anim_dir.exists():
        available = ", ".join(list_animations()) or "none"
        raise FileNotFoundError(f"Animation '{animation}' not found. Available: {available}")
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


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def make_background(size: tuple[int, int], bg_hex: str) -> Image.Image:
    """Clean solid pastel — no distracting blobs, just a very faint center glow."""
    hex_str = bg_hex.strip().lstrip("#")
    base = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    canvas = Image.new("RGBA", size, (*base, 255))
    # Faint lighter center glow for subtle depth
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    lighter = tuple(min(255, c + 18) for c in base)
    ImageDraw.Draw(glow).ellipse(
        (-80, size[1] // 4, size[0] + 80, size[1] * 3 // 4),
        fill=(*lighter, 55),
    )
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    return canvas


def draw_text_overlay(
    canvas: Image.Image,
    text: str,
    sub: str,
    size_key: str,
    alpha: int,
    w_scale: float,
) -> None:
    """Render text directly on canvas — no card/box, drop shadow only."""
    if not text and not sub:
        return

    main_px, sub_px = TEXT_SIZES.get(size_key, TEXT_SIZES["normal"])
    main_font = find_font(int(main_px * w_scale), bold=True)
    sub_font  = find_font(int(sub_px  * w_scale), bold=False)

    margin  = int(56 * w_scale)
    max_w   = canvas.width - margin * 2
    gap_ln  = int(10 * w_scale)   # between lines in a block
    gap_blk = int(20 * w_scale)   # between main and sub block

    proxy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    main_lines = wrap_text(proxy, text, main_font, max_w) if text else []
    sub_lines  = wrap_text(proxy, sub,  sub_font,  max_w) if sub  else []

    # Measure total block height so we can vertically center in the text zone
    total_h = 0
    for line in main_lines:
        total_h += measure(proxy, line, main_font)[1] + gap_ln
    if sub_lines:
        total_h += gap_blk
        for line in sub_lines:
            total_h += measure(proxy, line, sub_font)[1] + gap_ln

    # Text zone: top 27% of canvas — character lives below this
    zone_top = int(canvas.height * 0.06)
    zone_h   = int(canvas.height * 0.27)
    y = zone_top + max(0, (zone_h - total_h) // 2)

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw  = ImageDraw.Draw(layer)

    def render_line(line: str, font: ImageFont.ImageFont, color: tuple[int, int, int]) -> int:
        w, h = measure(draw, line, font)
        x = (canvas.width - w) // 2
        shadow_a = int(55 * alpha / 255)
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, shadow_a))
        draw.text((x, y), line, font=font, fill=(*color, alpha))
        return h + gap_ln

    nonlocal_y = [y]

    def next_line(line: str, font: ImageFont.ImageFont, color: tuple[int, int, int]) -> None:
        nonlocal_y[0] += render_line_at(draw, line, font, color, nonlocal_y[0], canvas.width, gap_ln, alpha)

    # Instead of the closure trick, just draw inline:
    for line in main_lines:
        w, h = measure(draw, line, main_font)
        x = (canvas.width - w) // 2
        draw.text((x + 2, y + 2), line, font=main_font, fill=(0, 0, 0, int(55 * alpha / 255)))
        draw.text((x, y), line, font=main_font, fill=(42, 42, 42, alpha))
        y += h + gap_ln

    if sub_lines:
        y += gap_blk
        for line in sub_lines:
            w, h = measure(draw, line, sub_font)
            x = (canvas.width - w) // 2
            draw.text((x + 1, y + 1), line, font=sub_font, fill=(0, 0, 0, int(40 * alpha / 255)))
            draw.text((x, y), line, font=sub_font, fill=(110, 110, 110, alpha))
            y += h + gap_ln

    canvas.alpha_composite(layer)



def render_video_frames(config: RenderConfig) -> list[Image.Image]:
    total_frames = max(1, int(config.duration * config.fps))
    w_scale = config.width / 720

    # Pre-load all animations referenced in beats
    anim_names = {config.default_animation} | {b.animation for b in config.beats if b.animation}
    anim_cache: dict[str, tuple[list[Image.Image], tuple[int, int]]] = {
        name: load_frames(name) for name in anim_names
    }

    # Sort and ensure a beat at t=0
    beats = sorted(config.beats, key=lambda b: b.time)
    if not beats or beats[0].time > 0:
        beats.insert(0, StoryBeat(time=0, text="", animation=config.default_animation))

    # Pre-compute irregular sprite schedule per animation
    sprite_schedules: dict[str, list[int]] = {
        name: make_sprite_schedule(total_frames, config.fps, len(frames))
        for name, (frames, _) in anim_cache.items()
    }

    # Load PNG watermark once, scaled to 42% of canvas width, semi-transparent
    wm_img: Image.Image | None = None
    if WATERMARK_PNG.exists():
        _wm = Image.open(WATERMARK_PNG).convert("RGBA")
        wm_target_w = int(config.width * 0.42)
        wm_ratio    = wm_target_w / _wm.width
        _wm = _wm.resize(
            (wm_target_w, max(1, int(_wm.height * wm_ratio))),
            Image.Resampling.LANCZOS,
        )
        # Apply global transparency (keep existing alpha, just scale it down)
        import numpy as np
        arr = np.array(_wm, dtype=np.float32)
        arr[:, :, 3] *= 0.48          # 48% opacity — readable but not distracting
        wm_img = Image.fromarray(arr.astype(np.uint8), "RGBA")

    TRANS   = 0.24   # character position/scale ease duration
    FADE_IN = 0.10   # text fade-in duration

    def beat_at(t: float) -> tuple[int, StoryBeat]:
        idx = 0
        for i, b in enumerate(beats):
            if b.time <= t:
                idx = i
        return idx, beats[idx]

    def anim_at(beat_idx: int) -> str:
        for i in range(beat_idx, -1, -1):
            if beats[i].animation:
                return beats[i].animation
        return config.default_animation

    rendered: list[Image.Image] = []

    for idx in range(total_frames):
        t = idx / config.fps
        beat_idx, beat = beat_at(t)
        age = t - beat.time

        # --- Sprite frame from pre-computed irregular schedule ---
        anim_name               = anim_at(beat_idx)
        sprite_frames, orig_size = anim_cache[anim_name]
        sprite                  = sprite_frames[sprite_schedules[anim_name][idx]].copy()
        orig_w, orig_h          = orig_size

        # --- Character position / scale with spring transition ---
        target_cx, target_cy = resolve_pos(beat.pos)
        target_scale = beat.scale

        if beat_idx > 0 and age < TRANS:
            prev   = beats[beat_idx - 1]
            pcx, pcy = resolve_pos(prev.pos)
            blend  = ease_out_cubic(age / TRANS)
            spring = ease_out_back(age / TRANS)
            char_cx    = lerp(pcx,        target_cx,    blend)
            char_cy    = lerp(pcy,        target_cy,    blend)
            char_scale = lerp(prev.scale, target_scale, spring)
        else:
            char_cx, char_cy, char_scale = target_cx, target_cy, target_scale

        # Scale punch on beat entry — brief +10% overshoot that settles
        if age < 0.20:
            char_scale *= 1.0 + 0.10 * math.sin(math.pi * age / 0.20)

        # ----------------------------------------------------------------
        # Organic motion — each signal has its own frequency and phase so
        # they never lock together and feel truly independent.
        # ----------------------------------------------------------------

        # Bob: slow organic float, never a perfect sine cycle
        bob_raw   = organic(t, freq=0.85, phase=0.00)
        bob_px    = bob_raw * 6 * w_scale                  # ±6px

        # Rotation: different freq so it drifts in/out of sync with bob
        rot_raw   = organic(t, freq=0.52, phase=1.91)
        rot_deg   = rot_raw * 4.0                          # ±4°

        # Breathing: very slow subtle scale pulse
        breath    = organic(t, freq=0.28, phase=3.77)
        char_scale *= 1.0 + breath * 0.018                # ±1.8%

        # Squash & stretch: tied to bob direction
        # — going down (bob_px > 0): slightly wider + shorter
        # — going up  (bob_px < 0): slightly narrower + taller
        sq_amount = bob_raw * 0.035
        sq_x = 1.0 + sq_amount                            # x widens when squashing
        sq_y = 1.0 - sq_amount                            # y shortens when squashing

        # ----------------------------------------------------------------
        # Compose frame
        # ----------------------------------------------------------------
        canvas = make_background((config.width, config.height), config.bg)

        # Text — fades in on beat entry
        text_alpha = min(255, int(255 * age / FADE_IN)) if age < FADE_IN else 255
        draw_text_overlay(canvas, beat.text, beat.sub, beat.text_size, text_alpha, w_scale)

        # Resize so the cat *body* (excluding padding) renders at 62% of
        # canvas width × char_scale.  The pre-upscaled sprite is padded_size×4,
        # so we scale relative to orig_size×4 — this is nearly always a
        # downscale from the pre-upscaled image, keeping edges sharp.
        target_cat_w = config.width * 0.62 * char_scale
        sf = target_cat_w / (orig_w * SPRITE_UPSCALE)

        new_w = max(1, int(sprite.width  * sf * sq_x))
        new_h = max(1, int(sprite.height * sf * sq_y))
        sprite = sprite.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Rotate after resize (cheaper; BICUBIC best available for rotate)
        if abs(rot_deg) > 0.3:
            sprite = sprite.rotate(rot_deg, expand=True, resample=Image.Resampling.BICUBIC)

        # Position without clamping — let the padding absorb any edge effects.
        # Composite only the visible portion so we never shift the cat's anchor.
        sx = int(config.width  * char_cx - sprite.width  // 2)
        sy = int(config.height * char_cy - sprite.height // 2 + bob_px)

        src_x0 = max(0, -sx);  src_x1 = min(sprite.width,  config.width  - sx)
        src_y0 = max(0, -sy);  src_y1 = min(sprite.height, config.height - sy)

        if src_x1 > src_x0 and src_y1 > src_y0:
            canvas.alpha_composite(
                sprite.crop((src_x0, src_y0, src_x1, src_y1)),
                (max(0, sx), max(0, sy)),
            )

        # PNG watermark — centred near bottom
        if wm_img is not None:
            wx = (config.width - wm_img.width) // 2
            wy = config.height - wm_img.height - int(90 * w_scale)
            canvas.alpha_composite(wm_img, (wx, max(0, wy)))

        rendered.append(canvas.convert("RGB"))

    return rendered


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_png_sequence(frames: list[Image.Image], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(frames):
        frame.save(out_dir / f"frame_{i:04d}.png")


def save_mp4(frames_dir: Path, mp4_path: Path, fps: int) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Run: pip install imageio-ffmpeg")
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%04d.png"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "slow",
            "-pix_fmt", "yuv420p",
            str(mp4_path),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr.decode()}")


def save_gif(frames: list[Image.Image], path: Path, fps: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ms = int(1000 / fps)
    pal = [f.convert("P", palette=Image.Palette.ADAPTIVE) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=ms, loop=0, disposal=2)


def slugify(value: str) -> str:
    out = []
    for ch in value.lower().strip().replace(" ", "_"):
        if ch.isalnum() or ch in {"_", "-"}:
            out.append(ch)
    return "".join(out).strip("_") or "dimsum_cat"


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

_VOWEL_SYLLABLE = {
    0:'아',1:'애',2:'야',3:'얘',4:'어',5:'에',6:'여',7:'예',
    8:'오',9:'와',10:'왜',11:'외',12:'요',13:'우',14:'워',
    15:'웨',16:'위',17:'유',18:'으',19:'의',20:'이',
}

def _elongate_korean(text: str, repeats: int = 2) -> str:
    """Append the last syllable's vowel sound repeated — 다 → 다아아."""
    clean = text.rstrip("!?~. ")
    suffix = text[len(clean):]
    for i in range(len(clean) - 1, -1, -1):
        code = ord(clean[i])
        if 0xAC00 <= code <= 0xD7A3:
            vowel_idx = ((code - 0xAC00) // 28) % 21
            vowel_syl = _VOWEL_SYLLABLE.get(vowel_idx, "")
            if vowel_syl:
                return clean + vowel_syl * repeats + suffix
            break
    return text


def _should_speak(text: str) -> bool:
    """Skip beats with no meaningful speech (punctuation-only, zzz, etc.)."""
    clean = text.strip()
    return bool(clean) and len(clean) >= 2 and not all(c in ".…zZ!? " for c in clean)


async def _edge_clip(text: str, voice: str, path: Path) -> None:
    import edge_tts  # type: ignore[import]
    # Deliver at slightly slower pace — ffmpeg handles pitch separately
    await edge_tts.Communicate(text, voice, rate="-12%").save(str(path))


def _detect_emotion(text: str) -> tuple[float, float, float]:
    """Return (speed_factor, temperature, repetition_penalty) based on emotion."""
    t = text.strip()
    if t.endswith("!!") or t.endswith("!!!"):
        return 1.15, 1.70, 1.15  # very excited / energetic
    if t.endswith("!"):
        return 1.06, 1.30, 1.25  # mild excitement
    if t in ("....", "...", "…"):
        return 0.75, 0.80, 1.4   # silent pause beat
    if ".." in t or "…" in t:
        return 0.82, 0.85, 1.35  # subdued / trailing off
    return 0.88, 1.10, 1.35      # neutral


def _has_repetition(text: str) -> bool:
    """Detect onomatopoeia or repeated syllable patterns like 두근두근, ㅋㅋㅋ."""
    import re
    # Check for Korean syllable repetition (e.g. 두근두근, 하하하)
    return bool(re.search(r'(.{1,3})\1', text))


def _gpt_sovits_clip(
    text: str,
    ref_audio: str,
    path: Path,
    server: str = "http://127.0.0.1:9880",
    speed: float | None = None,
    temperature: float | None = None,
) -> None:
    """Generate one clip via local GPT-SoVITS API server."""
    import requests  # type: ignore[import]
    auto_speed, auto_temp, auto_rep = _detect_emotion(text)
    # Lower repetition_penalty for onomatopoeia so repeated syllables don't get cut
    rep_penalty = 1.05 if _has_repetition(text) else auto_rep
    resp = requests.post(f"{server}/tts", json={
        "text": text,
        "text_lang": "ko",
        "ref_audio_path": ref_audio,
        "prompt_lang": "ko",
        "prompt_text": "",
        "speed_factor":        speed       if speed       is not None else auto_speed,
        "temperature":         temperature if temperature is not None else auto_temp,
        "repetition_penalty":  rep_penalty,
        "top_k": 10,
        "streaming_mode": False,
        "batch_size": 1,
    }, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"GPT-SoVITS error {resp.status_code}: {resp.text}")
    path.with_suffix(".wav").write_bytes(resp.content)



def _audio_duration(ffmpeg: str, path: Path) -> float:
    """Return duration in seconds of an audio file using ffmpeg."""
    r = subprocess.run(
        [ffmpeg, "-i", str(path), "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    for line in r.stderr.decode(errors="replace").splitlines():
        if "Duration:" in line:
            t = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = t.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
    return 0.0


def _recalculate_beat_times(
    beats: list[StoryBeat],
    clip_durations: dict[int, float],
    intro_gap: float = 0.6,
    between_gap: float = 0.30,
    silent_beat_dur: float = 1.5,
) -> tuple[list[StoryBeat], float]:
    """Retime beats so each scene ends shortly after its speech finishes.

    Beats with speech advance by (clip_duration + between_gap).
    Beats without speech (punctuation, silent) advance by silent_beat_dur.
    """
    new_beats: list[StoryBeat] = []
    t = intro_gap
    for i, beat in enumerate(beats):
        new_beats.append(dataclasses.replace(beat, time=t))
        dur = clip_durations.get(i, 0.0)
        t += (dur + between_gap) if dur > 0 else silent_beat_dur
    return new_beats, t + 0.8   # trailing buffer


def build_tts_audio(
    beats: list,
    duration: float,
    provider: str,
    voice: str,
    out_path: Path,
    gpt_sovits_ref: str = "",
    gpt_sovits_server: str = "http://127.0.0.1:9880",
    gpt_sovits_speed: float = 0.88,
    return_durations: bool = False,
    pregenerated_dir: Path | None = None,
) -> bool | dict:
    """Generate a timed audio track from beat texts using ffmpeg filter_complex.

    Supports "edge" (free, less expressive) and "gpt_sovits" (local voice cloning).
    Clips are mixed at the correct timestamps via ffmpeg adelay+amix — no ffprobe needed.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("  TTS skipped: ffmpeg not found")
        return False

    tmp_dir = pregenerated_dir if pregenerated_dir else out_path.parent / "_tts_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Collect indices + beats that need speech
    speak_beats = [(i, b) for i, b in enumerate(beats) if _should_speak(b.text)]
    if not speak_beats:
        print("  TTS skipped: no speakable beats")
        if not pregenerated_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return False

    # ── Generate clips (skipped if pregenerated_dir is provided) ────────────
    if not pregenerated_dir:
        if provider == "gpt_sovits":
            ref, server, speed = gpt_sovits_ref, gpt_sovits_server, gpt_sovits_speed
            if not ref:
                print("  TTS skipped: gpt_sovits_ref not set")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False
            try:
                for i, b in speak_beats:
                    print(f"    GPT-SoVITS: {b.text}")
                    _gpt_sovits_clip(b.text, ref, tmp_dir / f"beat_{i:02d}.wav",
                                     server=server,
                                     speed=b.tts_speed,
                                     temperature=b.tts_temperature)
            except Exception as e:
                print(f"  TTS (GPT-SoVITS) failed: {e}")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False
            for i, _ in speak_beats:
                wav = tmp_dir / f"beat_{i:02d}.wav"
                if wav.exists():
                    subprocess.run(
                        [ffmpeg, "-y", "-i", str(wav),
                         "-c:a", "libmp3lame", "-b:a", "128k",
                         str(tmp_dir / f"beat_{i:02d}.mp3")],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    )
                    wav.unlink(missing_ok=True)

        else:  # edge-tts
            try:
                import edge_tts  # noqa: F401
            except ImportError as e:
                print(f"  TTS skipped: {e}")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False

            async def _gen_all() -> None:
                tasks = [
                    _edge_clip(b.text, voice, tmp_dir / f"beat_{i:02d}.mp3")
                    for i, b in speak_beats
                ]
                await asyncio.gather(*tasks)

            asyncio.run(_gen_all())

    # ── Post-process GPT-SoVITS clips: remove breathiness ────────────────────
    # highpass=f=130  → cuts low-frequency breath/rumble
    # dynaudnorm      → evens out loud/quiet moments so voice sounds consistent
    if provider == "gpt_sovits" and not pregenerated_dir:
        for i, _ in speak_beats:
            p = tmp_dir / f"beat_{i:02d}.mp3"
            if not p.exists():
                continue
            tmp_p = tmp_dir / f"beat_{i:02d}_c.mp3"
            subprocess.run(
                [ffmpeg, "-y", "-i", str(p),
                 "-af", "afade=t=in:st=0:d=0.06,highpass=f=130,dynaudnorm=g=11:p=0.92:m=80",
                 "-c:a", "libmp3lame", "-b:a", "128k", str(tmp_p)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if tmp_p.exists():
                tmp_p.replace(p)

    # ── Collect clips that were actually written ──────────────────────────────
    clip_list = [
        (i, b) for i, b in speak_beats
        if (tmp_dir / f"beat_{i:02d}.mp3").exists()
    ]

    if not clip_list:
        print("  TTS skipped: no clips generated")
        if not pregenerated_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return False

    # ── Phase 1 mode: measure durations and return them (no mix yet) ─────────
    if return_durations:
        durations = {
            i: _audio_duration(ffmpeg, tmp_dir / f"beat_{i:02d}.mp3")
            for i, _ in clip_list
        }
        return durations

    # ── Pitch shift for edge-tts only ────────────────────────────────────────
    for i, _ in clip_list if provider != "gpt_sovits" else []:
        p = tmp_dir / f"beat_{i:02d}.mp3"
        tmp_p = tmp_dir / f"beat_{i:02d}_p.mp3"
        subprocess.run(
            [ffmpeg, "-y", "-i", str(p),
             "-af", "asetrate=44100*1.55,aresample=44100,atempo=0.645,highpass=f=160",
             str(tmp_p)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if tmp_p.exists():
            tmp_p.replace(p)

    # ── Fade-out each clip ────────────────────────────────────────────────────
    for idx, (i, beat) in enumerate(clip_list):
        p = tmp_dir / f"beat_{i:02d}.mp3"
        next_time = clip_list[idx + 1][1].time if idx + 1 < len(clip_list) else duration
        max_dur = next_time - beat.time - 0.20
        if max_dur <= 0:
            continue
        clip_dur = _audio_duration(ffmpeg, p)
        trim_dur = min(clip_dur, max_dur)
        fade_dur = min(0.18, trim_dur * 0.15)
        tmp_p = tmp_dir / f"beat_{i:02d}_t.mp3"
        subprocess.run(
            [ffmpeg, "-y", "-i", str(p),
             "-af", f"atrim=end={trim_dur:.3f},afade=t=out:st={trim_dur - fade_dur:.3f}:d={fade_dur:.3f}",
             "-c:a", "libmp3lame", "-b:a", "128k", str(tmp_p)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if tmp_p.exists():
            tmp_p.replace(p)

    # Build ffmpeg command using filter_complex — no ffprobe needed.
    # anullsrc creates the silent base; each clip gets adelay to shift it to
    # the correct beat timestamp; amix combines everything.
    ffmpeg_inputs: list[str] = []
    filter_parts = [
        f"anullsrc=r=44100:cl=stereo,atrim=duration={duration}[base]"
    ]
    mix_labels = ["[base]"]

    for j, (i, beat) in enumerate(clip_list):
        p = tmp_dir / f"beat_{i:02d}.mp3"
        delay_ms = int(beat.time * 1000)
        ffmpeg_inputs += ["-i", str(p)]
        filter_parts.append(f"[{j}]adelay={delay_ms}|{delay_ms}[a{j}]")
        mix_labels.append(f"[a{j}]")

    n = len(mix_labels)
    filter_parts.append(
        f"{''.join(mix_labels)}amix=inputs={n}:normalize=0:duration=first"
    )
    filter_complex = ";".join(filter_parts)

    result = subprocess.run(
        [ffmpeg, "-y"] + ffmpeg_inputs + [
            "-filter_complex", filter_complex,
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(out_path),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # Clean up tmp_dir only if we own it (not pregenerated_dir from render())
    if not pregenerated_dir:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if result.returncode != 0:
        print(f"  TTS audio mix failed:\n{result.stderr.decode()}")
        return False

    return True


def mux_audio_into_mp4(
    mp4_path: Path,
    audio_path: Path,
    bg_music: Path | None = None,
    bg_volume: float = 0.09,
) -> None:
    """Mux TTS audio (+ optional background music) into MP4 in-place.

    bg_music loops automatically to match the video length.
    bg_volume controls the relative level of the background track (0–1).
    """
    ffmpeg = find_ffmpeg()
    tmp = mp4_path.with_suffix(".tmp.mp4")

    if bg_music and bg_music.exists():
        # stream_loop -1 loops the music file indefinitely;
        # -shortest stops everything when the video ends.
        # TTS track is boosted slightly; bgm sits quietly underneath.
        result = subprocess.run(
            [ffmpeg, "-y",
             "-i", str(mp4_path),
             "-i", str(audio_path),
             "-stream_loop", "-1", "-i", str(bg_music),
             "-filter_complex",
             f"[1]volume=1.4[tts];[2]volume={bg_volume}[bgm];"
             "[tts][bgm]amix=inputs=2:normalize=0:dropout_transition=0[aout]",
             "-map", "0:v", "-map", "[aout]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
             str(tmp)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    else:
        result = subprocess.run(
            [ffmpeg, "-y",
             "-i", str(mp4_path),
             "-i", str(audio_path),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
             str(tmp)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed:\n{result.stderr.decode()}")
    tmp.replace(mp4_path)


def render(config: RenderConfig) -> dict:
    # Output goes into the story's own folder; fallback to content/<name>
    out_base = config.story_dir if config.story_dir else CONTENT_ROOT / config.output_name
    out_base.mkdir(parents=True, exist_ok=True)
    frames_dir = out_base / "frames"
    # Clear stale frames from previous renders so old frames don't extend duration
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    mp4_path = out_base / "video.mp4"
    gif_path = out_base / "video.gif"

    # Resolve background music path early
    bg_music_path: Path | None = None
    if config.bg_music:
        p = Path(config.bg_music)
        bg_music_path = p if p.is_absolute() else ROOT / p
        if not bg_music_path.exists():
            print(f"  WARNING: bg_music not found: {bg_music_path}")
            bg_music_path = None

    # ── Phase 1: TTS pre-generation (before rendering video frames) ──────────
    # Generate clips first so we can measure their actual durations and retime
    # the beats — each scene stays on screen exactly as long as the speech.
    audio_path: Path | None = None
    tts_ok = False
    if config.tts:
        print("  Generating TTS audio...")
        audio_path = out_base / f"{config.output_name}_audio.mp3"
        tts_ok = build_tts_audio(
            config.beats, config.duration,
            provider=config.tts_provider,
            voice=config.tts_voice,
            out_path=audio_path,
            gpt_sovits_ref=config.gpt_sovits_ref,
            gpt_sovits_server=config.gpt_sovits_server,
            gpt_sovits_speed=config.gpt_sovits_speed,
            return_durations=True,
        )
        if isinstance(tts_ok, dict):
            # Retime beats based on actual clip durations
            clip_durations: dict[int, float] = tts_ok
            new_beats, new_duration = _recalculate_beat_times(config.beats, clip_durations)
            config = dataclasses.replace(config, beats=new_beats, duration=new_duration)
            tts_ok = True  # clips are in out_base/_tts_tmp, mix happens after render

    # ── Phase 2: Render video frames with (retimed) config ───────────────────
    frames = render_video_frames(config)
    save_png_sequence(frames, frames_dir)
    save_mp4(frames_dir, mp4_path, config.fps)

    # ── Phase 3: Mix TTS audio at retimed timestamps + mux ───────────────────
    if config.tts:
        if tts_ok:
            mix_ok = build_tts_audio(
                config.beats, config.duration,
                provider=config.tts_provider,
                voice=config.tts_voice,
                out_path=audio_path,
                gpt_sovits_ref=config.gpt_sovits_ref,
                gpt_sovits_server=config.gpt_sovits_server,
                gpt_sovits_speed=config.gpt_sovits_speed,
                pregenerated_dir=out_base / "_tts_tmp",
            )
            shutil.rmtree(out_base / "_tts_tmp", ignore_errors=True)
            if mix_ok:
                mux_audio_into_mp4(mp4_path, audio_path, bg_music=bg_music_path)
                audio_path.unlink(missing_ok=True)
                suffix = " + background music" if bg_music_path else ""
                print(f"  TTS muxed into MP4{suffix}.")
            else:
                print("  TTS mix failed — video saved without audio.")
        else:
            print("  TTS failed — video saved without audio.")
    elif bg_music_path:
        # Background music only (no TTS)
        print("  Adding background music...")
        silence = out_base / "_silence.mp3"
        ffmpeg = find_ffmpeg()
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi",
             "-i", f"anullsrc=r=44100:cl=stereo,atrim=duration={config.duration}",
             "-c:a", "libmp3lame", "-b:a", "64k", str(silence)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        mux_audio_into_mp4(mp4_path, silence, bg_music=bg_music_path)
        silence.unlink(missing_ok=True)
        print("  Background music muxed into MP4.")

    gif_created = False
    if config.save_gif:
        save_gif(frames, gif_path, config.fps)
        gif_created = True

    return {"frames_dir": frames_dir, "mp4": mp4_path, "gif": gif_path if gif_created else None}


def print_result(result: dict) -> None:
    print(f"  Frames : {result['frames_dir']}")
    print(f"  MP4    : {result['mp4']}")
    if result.get("gif"):
        print(f"  GIF    : {result['gif']}")


# ---------------------------------------------------------------------------
# Story loading
# ---------------------------------------------------------------------------

DEFAULT_STORY = [
    StoryBeat(time=0.0,  text="진짜..?",    sub="Really..?",
              animation="normal_talk",  pos="center",     scale=1.0,  text_size="big"),
    StoryBeat(time=3.0,  text="나 좋아해?", sub="You like me?",
              animation="shy_blush",    pos="right",      scale=1.25, text_size="huge"),
    StoryBeat(time=6.5,  text="ㅋㅋㅋ",     sub="lol",
              animation="excited_talk", pos="center-low", scale=0.85, text_size="normal"),
    StoryBeat(time=9.5,  text="❤",          sub="",
              animation="finger_heart", pos="center",     scale=1.4,  text_size="huge"),
]


def _resolve_story_path(raw: str, story_dir: Path) -> str:
    """Resolve a path that may be relative to the story folder or project root."""
    if not raw:
        return raw
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    # Try relative to story folder first, then project root
    rel_to_story = (story_dir / p).resolve()
    if rel_to_story.exists():
        return str(rel_to_story)
    rel_to_root = (ROOT / p).resolve()
    return str(rel_to_root)


def load_story_json(path: Path, args: argparse.Namespace) -> RenderConfig:
    # Accept directory path → look for story.json inside
    if path.is_dir():
        path = path / "story.json"
    path = path.resolve()
    story_dir = path.parent

    data = json.loads(path.read_text(encoding="utf-8"))
    raw_beats = data.get("beats", [])
    beats = [
        StoryBeat(
            time            = b["time"],
            text            = b.get("text", ""),
            sub             = b.get("sub", ""),
            animation       = b.get("animation", ""),
            pos             = b.get("pos", "center"),
            scale           = float(b.get("scale", 1.0)),
            text_size       = b.get("text_size", "normal"),
            tts_speed       = float(b["tts_speed"])       if "tts_speed"       in b else None,
            tts_temperature = float(b["tts_temperature"]) if "tts_temperature" in b else None,
        )
        for b in raw_beats
    ]
    output_name = data.get("output", args.output) or story_dir.name
    return RenderConfig(
        beats             = beats,
        default_animation = data.get("animation", args.animation),
        output_name       = output_name,
        story_dir         = story_dir,
        duration          = float(data.get("duration", args.duration)),
        fps               = int(data.get("fps", args.fps)),
        width             = int(data.get("width", args.width)),
        height            = int(data.get("height", args.height)),
        bg                = data.get("bg", args.bg),
        watermark         = data.get("watermark", args.watermark),
        save_gif          = args.gif,
        tts               = data.get("tts", args.tts),
        tts_provider      = data.get("tts_provider", args.tts_provider),
        tts_voice         = data.get("tts_voice", args.tts_voice),
        gpt_sovits_ref    = _resolve_story_path(data.get("gpt_sovits_ref", args.gpt_sovits_ref), story_dir),
        gpt_sovits_server = data.get("gpt_sovits_server", args.gpt_sovits_server),
        gpt_sovits_speed  = float(data.get("gpt_sovits_speed", args.gpt_sovits_speed)),
        bg_music          = _resolve_story_path(data.get("bg_music", args.bg_music), story_dir),
    )


def config_from_args(args: argparse.Namespace) -> RenderConfig:
    # Build a single-beat story from simple CLI flags
    beat = StoryBeat(
        time      = 0,
        text      = args.text,
        sub       = args.sub,
        animation = args.animation,
        pos       = args.pos,
        scale     = args.scale,
        text_size = args.text_size,
    )
    output_name = args.output or slugify(args.text or args.animation)
    return RenderConfig(
        beats             = [beat],
        default_animation = args.animation,
        output_name       = output_name,
        duration          = args.duration,
        fps               = args.fps,
        width             = args.width,
        height            = args.height,
        bg                = args.bg,
        watermark         = args.watermark,
        save_gif          = args.gif,
        tts               = args.tts,
        tts_provider      = args.tts_provider,
        tts_voice         = args.tts_voice,
        gpt_sovits_ref    = args.gpt_sovits_ref,
        gpt_sovits_server = args.gpt_sovits_server,
        gpt_sovits_speed  = args.gpt_sovits_speed,
        bg_music          = args.bg_music,
    )


def config_demo(args: argparse.Namespace) -> RenderConfig:
    output_name = args.output or "demo_story"
    return RenderConfig(
        beats             = DEFAULT_STORY,
        default_animation = "normal_talk",
        output_name       = output_name,
        duration          = args.duration,
        fps               = args.fps,
        width             = args.width,
        height            = args.height,
        bg                = args.bg,
        watermark         = args.watermark,
        save_gif          = args.gif,
        tts               = args.tts,
        tts_provider      = args.tts_provider,
        tts_voice         = args.tts_voice,
        gpt_sovits_ref    = args.gpt_sovits_ref,
        gpt_sovits_server = args.gpt_sovits_server,
        gpt_sovits_speed  = args.gpt_sovits_speed,
        bg_music          = args.bg_music,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Render DIMsum Cat short-form vertical videos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Story mode (recommended):
  python video_generator.py --story my_story.json

Quick single-beat:
  python video_generator.py --text "你好" --sub "nǐ hǎo · Hello" --animation normal_talk

Demo (built-in 4-beat story):
  python video_generator.py --demo
""",
    )
    p.add_argument("--list-animations", action="store_true", help="List available animations and exit.")
    p.add_argument("--demo",   action="store_true", help="Render the built-in demo story.")
    p.add_argument("--story",  type=Path,           help="Path to a story JSON file.")

    # Single-beat quick mode
    p.add_argument("--text",      default="你好可爱",         help="Main text.")
    p.add_argument("--sub",       default="nǐ hǎo kě ài",   help="Secondary/translation text.")
    p.add_argument("--animation", default="normal_talk",     help="Animation name.")
    p.add_argument("--pos",       default="center",          help="Character position (named or cx,cy).")
    p.add_argument("--scale",     type=float, default=1.0,   help="Character scale multiplier.")
    p.add_argument("--text-size", dest="text_size", default="big",
                   choices=list(TEXT_SIZES), help="Text size preset.")

    # Shared output settings
    p.add_argument("--output",   default="",       help="Output folder name under output/.")
    p.add_argument("--duration", type=float, default=12.0,  help="Video duration in seconds.")
    p.add_argument("--fps",      type=int,   default=24,    help="Frames per second.")
    p.add_argument("--width",    type=int,   default=1080,  help="Canvas width.")
    p.add_argument("--height",   type=int,   default=1920,  help="Canvas height.")
    p.add_argument("--bg",       default="#f8f4f0",         help="Background hex color.")
    p.add_argument("--watermark", default="",               help="(unused — watermark.png is used instead)")
    p.add_argument("--gif",       action="store_true",        help="Also export a GIF preview.")
    p.add_argument("--tts",              action="store_true",                   help="Add TTS voiceover.")
    p.add_argument("--tts-provider",     default="edge",       dest="tts_provider",
                   choices=["edge", "gpt_sovits"],             help="TTS provider (default: edge).")
    p.add_argument("--tts-voice",        default=TTS_VOICE_DEFAULT, dest="tts_voice",
                                                               help="edge-tts voice name.")
    p.add_argument("--gpt-sovits-ref",    default="",           dest="gpt_sovits_ref",
                                                               help="Reference audio for GPT-SoVITS voice cloning (3-10s).")
    p.add_argument("--gpt-sovits-server", default="http://127.0.0.1:9880", dest="gpt_sovits_server",
                                                               help="GPT-SoVITS API server URL.")
    p.add_argument("--gpt-sovits-speed",  default=0.88, type=float, dest="gpt_sovits_speed",
                                                               help="Speech speed for GPT-SoVITS (default 0.88).")
    p.add_argument("--bg-music",         default="",           dest="bg_music",
                                                               help="Path to background music file. Loops automatically.")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_animations:
        for name in list_animations():
            print(name)
        return

    if args.demo:
        result = render(config_demo(args))
    elif args.story:
        result = render(load_story_json(args.story, args))
    else:
        result = render(config_from_args(args))

    print_result(result)


if __name__ == "__main__":
    main()
