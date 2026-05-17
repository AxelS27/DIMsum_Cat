from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from src.models import (
    RenderConfig,
    RichTextSpan,
    StoryBeat,
    WATERMARK_PNG,
    TEXT_SIZES,
    SPRITE_UPSCALE,
)
from src.utils import (
    resolve_pos,
    find_font,
    measure,
    wrap_text,
    lerp,
    ease_out_cubic,
    ease_out_back,
)
from src.sprite import organic, make_sprite_schedule, load_frames


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


def _parse_hex_color(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    raw = value.strip().lstrip("#")
    if len(raw) != 6:
        return fallback
    try:
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def _measure_rich_line(
    draw: ImageDraw.ImageDraw,
    spans: list[RichTextSpan],
    font,
) -> tuple[int, int]:
    width = 0
    height = 0
    for span in spans:
        w, h = measure(draw, span.text, font)
        width += w
        height = max(height, h)
    return width, height


def _draw_rich_line(
    draw: ImageDraw.ImageDraw,
    spans: list[RichTextSpan],
    font,
    x: int,
    y: int,
    alpha: int,
) -> None:
    cursor = x
    shadow_a = int(70 * alpha / 255)
    for span in spans:
        color = _parse_hex_color(span.color, (42, 42, 42))
        draw.text((cursor + 3, y + 3), span.text, font=font, fill=(0, 0, 0, shadow_a))
        draw.text((cursor, y), span.text, font=font, fill=(*color, alpha))
        cursor += measure(draw, span.text, font)[0]


def draw_text_overlay(
    canvas: Image.Image,
    text: str,
    sub: str,
    size_key: str,
    alpha: int,
    w_scale: float,
    rich_text: list[RichTextSpan] | None = None,
) -> None:
    """Render text directly on canvas — no card/box, drop shadow only."""
    rich_text = rich_text or []
    if not text and not sub and not rich_text:
        return

    main_px, sub_px = TEXT_SIZES.get(size_key, TEXT_SIZES["normal"])
    main_font = find_font(int(main_px * w_scale), bold=True)
    sub_font  = find_font(int(sub_px  * w_scale), bold=False)

    margin  = int(56 * w_scale)
    max_w   = canvas.width - margin * 2
    gap_ln  = int(10 * w_scale)   # between lines in a block
    gap_blk = int(20 * w_scale)   # between main and sub block

    proxy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    main_lines = [] if rich_text else (wrap_text(proxy, text, main_font, max_w) if text else [])
    sub_lines  = wrap_text(proxy, sub,  sub_font,  max_w) if sub  else []

    if rich_text:
        rich_w, _ = _measure_rich_line(proxy, rich_text, main_font)
        if rich_w > max_w:
            scale = max(0.68, max_w / rich_w)
            main_font = find_font(max(1, int(main_px * w_scale * scale)), bold=True)

    # Measure total block height so we can vertically center in the text zone
    total_h = 0
    if rich_text:
        total_h += _measure_rich_line(proxy, rich_text, main_font)[1] + gap_ln
    else:
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
    if rich_text:
        w, h = _measure_rich_line(draw, rich_text, main_font)
        x = (canvas.width - w) // 2
        _draw_rich_line(draw, rich_text, main_font, x, y, alpha)
        y += h + gap_ln
    else:
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
        draw_text_overlay(canvas, beat.text, beat.sub, beat.text_size, text_alpha, w_scale, beat.rich_text)

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
