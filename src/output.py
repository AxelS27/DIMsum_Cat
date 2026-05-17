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
