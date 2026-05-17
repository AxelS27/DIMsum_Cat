from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.models import StoryBeat
from src.utils import find_ffmpeg, _audio_duration

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


def build_tts_audio(
    beats: list,
    duration: float,
    out_path: Path,
    gpt_sovits_ref: str = "",
    gpt_sovits_server: str = "http://127.0.0.1:9880",
    gpt_sovits_speed: float = 0.88,
    return_durations: bool = False,
    pregenerated_dir: Path | None = None,
) -> bool | dict:
    """Generate a timed audio track from beat texts using ffmpeg filter_complex.

    Uses GPT-SoVITS (local voice cloning) for TTS generation.
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

    # ── Post-process clips: remove breathiness ───────────────────────────────
    # highpass=f=130  → cuts low-frequency breath/rumble
    # dynaudnorm      → evens out loud/quiet moments so voice sounds consistent
    if not pregenerated_dir:
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
