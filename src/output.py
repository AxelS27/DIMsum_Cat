from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from src.utils import find_ffmpeg


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_png_sequence(frames: list[Image.Image], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(frames):
        frame.save(out_dir / f"frame_{i:04d}.png")


def save_mp4(
    frames_dir: Path,
    mp4_path: Path,
    fps: int,
    title: str = "",
    description: str = "",
) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Run: pip install imageio-ffmpeg")
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = []
    if title:
        metadata += ["-metadata", f"title={title}"]
    if description:
        metadata += ["-metadata", f"comment={description}"]
    result = subprocess.run(
        [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%04d.png"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "h264_nvenc",
            "-cq", "18",
            "-preset", "p4",
            "-rc", "vbr",
            "-pix_fmt", "yuv420p",
            *metadata,
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


def _parse_music_start(s: str) -> float:
    """Parse 'SS:cs' (seconds:centiseconds) to float seconds. '12:50' → 12.50s"""
    if not s:
        return 0.0
    parts = s.split(":")
    try:
        secs = int(parts[0])
        cs   = int(parts[1]) if len(parts) > 1 else 0
        return secs + cs / 100.0
    except (ValueError, IndexError):
        return 0.0


def mux_audio_into_mp4(
    mp4_path: Path,
    audio_path: Path,
    bg_music: Path | None = None,
    bg_volume: float = 0.09,
    bg_music_start: str = "",
    tts_volume: float = 1.4,
) -> None:
    """Mux TTS audio (+ optional background music) into MP4 in-place.

    bg_music loops automatically to match the video length.
    bg_volume controls the relative level of the background track (0–1).
    bg_music_start: "SS:cs" offset into the music file before looping.
    """
    ffmpeg = find_ffmpeg()
    tmp = mp4_path.with_suffix(".tmp.mp4")

    if bg_music and bg_music.exists():
        start_sec = _parse_music_start(bg_music_start)
        ss_args = ["-ss", f"{start_sec:.3f}"] if start_sec > 0 else []
        # stream_loop -1 loops the music file indefinitely;
        # -shortest stops everything when the video ends.
        # TTS track is boosted slightly; bgm sits quietly underneath.
        result = subprocess.run(
            [ffmpeg, "-y",
             "-i", str(mp4_path),
             "-i", str(audio_path),
             "-stream_loop", "-1", *ss_args, "-i", str(bg_music),
             "-filter_complex",
             f"[1]volume={tts_volume}[tts];[2]volume={bg_volume}[bgm];"
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


def mix_audio_preview(
    tts_path: Path,
    out_path: Path,
    bg_music: Path | None = None,
    bg_volume: float = 0.09,
    bg_music_start: str = "",
    tts_volume: float = 1.4,
) -> None:
    """Mix TTS audio with optional bg_music into a standalone mp3 (no video)."""
    ffmpeg = find_ffmpeg()
    if bg_music and bg_music.exists():
        start_sec = _parse_music_start(bg_music_start)
        ss_args = ["-ss", f"{start_sec:.3f}"] if start_sec > 0 else []
        result = subprocess.run(
            [ffmpeg, "-y",
             "-i", str(tts_path),
             "-stream_loop", "-1", *ss_args, "-i", str(bg_music),
             "-filter_complex",
             f"[0]volume={tts_volume}[tts];[1]volume={bg_volume}[bgm];"
             "[tts][bgm]amix=inputs=2:normalize=0:dropout_transition=0:duration=first[aout]",
             "-map", "[aout]",
             "-c:a", "libmp3lame", "-b:a", "128k",
             str(out_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    else:
        import shutil as _shutil
        _shutil.copy2(tts_path, out_path)
        return
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mix failed:\n{result.stderr.decode()}")
