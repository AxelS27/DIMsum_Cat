from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 output so Korean text doesn't crash on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from src.models import (
    RenderConfig,
    StoryBeat,
    ROOT,
    CONTENT_ROOT,
    TEXT_SIZES,
)
from src.utils import (
    find_ffmpeg,
    list_animations,
    slugify,
    _recalculate_beat_times,
)
from src.renderer import render_video_frames
from src.sprite import load_frames
from src.tts import build_tts_audio
from src.output import (
    save_png_sequence,
    save_mp4,
    save_gif,
    mux_audio_into_mp4,
)

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
        title             = data.get("title", ""),
        description       = data.get("description", ""),
        duration          = float(data.get("duration", args.duration)),
        fps               = int(data.get("fps", args.fps)),
        width             = int(data.get("width", args.width)),
        height            = int(data.get("height", args.height)),
        bg                = data.get("bg", args.bg),
        watermark         = data.get("watermark", args.watermark),
        save_gif          = args.gif,
        tts               = data.get("tts", args.tts),
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
    p.add_argument("--gpt-sovits-ref",    default="",           dest="gpt_sovits_ref",
                                                               help="Reference audio for GPT-SoVITS voice cloning (3-10s).")
    p.add_argument("--gpt-sovits-server", default="http://127.0.0.1:9880", dest="gpt_sovits_server",
                                                               help="GPT-SoVITS API server URL.")
    p.add_argument("--gpt-sovits-speed",  default=0.88, type=float, dest="gpt_sovits_speed",
                                                               help="Speech speed for GPT-SoVITS (default 0.88).")
    p.add_argument("--bg-music",         default="",           dest="bg_music",
                                                               help="Path to background music file. Loops automatically.")
    return p


def print_result(result: dict) -> None:
    print(f"  Frames : {result['frames_dir']}")
    print(f"  MP4    : {result['mp4']}")
    if result.get("gif"):
        print(f"  GIF    : {result['gif']}")


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
    save_mp4(frames_dir, mp4_path, config.fps, title=config.title, description=config.description)

    # ── Phase 3: Mix TTS audio at retimed timestamps + mux ───────────────────
    if config.tts:
        if tts_ok:
            mix_ok = build_tts_audio(
                config.beats, config.duration,
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
