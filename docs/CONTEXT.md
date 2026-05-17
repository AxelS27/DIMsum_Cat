# DIMsum Cat — Project Context

> Kawaii animated cat character for short-form Korean content on Instagram Reels, TikTok, and YouTube Shorts.

## Character

**DIMsum Cat** is a cute kawaii cat girl. Pronoun: **she/her**.
Brand handle: `@dimsumcat.studio`

The character is expressive, relatable, and a little dramatic — perfect for storytelling, reactions, and Korean pop culture content.

## Platforms

- Instagram Reels (primary)
- TikTok
- YouTube Shorts

Format: **1080×1920 Full HD, 24fps, vertical 9:16**

---

## Tech Stack

| Component | Tool |
|-----------|------|
| Renderer | `video_generator.py` → `src/` package |
| TTS | GPT-SoVITS (local, voice cloned from `assets/audio_reference/`) |
| Sprite extraction | `scripts/extract_sprites.py` |
| Font | Jua (cute rounded Korean font) |
| Output | `content/<story_name>/video.mp4` |

### Running

```bash
# Start GPT-SoVITS API server first
D:/GPT-SoVITS/runtime/python.exe D:/GPT-SoVITS/api_v2.py -a 127.0.0.1 -p 9880

# Render a story
.venv/Scripts/python video_generator.py --story content/story_crush
```

---

## Project Structure

```
assets/
  audio_reference/        ← voice reference audio (gitignored)
    dimsum_cat_korean.mp3
  fonts/
    Jua-Regular.ttf
  music/
    love_maybe.mp3
  sprites/
    watermark.png
    dimsum_cat/
      animations/         ← 60 animation folders (frame_a–d.png each)
      design/             ← original design sheets (design_1–5.png)

content/
  _template/              ← copy this to start a new story
    story.json
  story_crush/            ← example story
    story.json
    video.mp4             ← rendered output (gitignored)
    frames/               ← temp PNG frames during render (gitignored)

docs/
  CONTEXT.md              ← this file
  CONTENT.md              ← content strategy & ideas
  reference_videos/       ← style reference videos
    video_1.mp4
    video_2.mp4

scripts/
  extract_sprites.py      ← extract frames from design sheets

src/
  __init__.py
  models.py               ← StoryBeat, RenderConfig, constants
  utils.py                ← helpers, font, ffmpeg
  sprite.py               ← organic motion, load_frames
  renderer.py             ← render_video_frames, text overlay
  tts.py                  ← GPT-SoVITS TTS, emotion detection
  output.py               ← save_mp4, mux_audio
  story.py                ← load_story_json, CLI, main()

video_generator.py        ← entry point (3 lines)
.env                      ← API keys (gitignored)
.venv/                    ← Python virtual environment (gitignored)
```

---

## Animation Library (60 total)

**Original 12:** normal_talk, excited_talk, whisper_secret, wink, blow_kiss, heart_eyes, shy_blush, finger_heart, smirk, holding_phone, waiting_reply, got_a_text

**Extended 48:** crying, angry_pout, sleepy_yawn, shocked, confused_thinking, laughing_hard, embarrassed, panic, dizzy, sick_fever, determined, mischief_grin, facepalm, pleading, proud, nervous_sweat, peekaboo, cheering, hugging_pillow, thumbs_up, clapping, salute, need_a_hug, sassy_pose, sulking, begging, sniffling, startled_jump, want_attention, self_hug, side_eye, tiny_tantrum, cozy_blanket, stretching, tongue_out_tease, happy_wiggle, head_tilt, little_wave, curious_peek, daydreaming, rubbing_eyes, tiny_giggle, happy_bounce, listening_closely, tiny_stretch_sit, blow_air_hmph, peek_from_box, mini_twirl

---

## Story JSON Format

Each story lives in `content/<name>/story.json`. Key fields:

```json
{
  "title": "English title for MP4 metadata",
  "description": "Caption + hashtags for Instagram/TikTok",
  "animation": "normal_talk",
  "bg": "#f5f0ec",
  "tts": true,
  "gpt_sovits_ref": "../../assets/audio_reference/dimsum_cat_korean.mp3",
  "bg_music": "../../assets/music/love_maybe.mp3",
  "beats": [
    {
      "time": 0.0,
      "text": "Korean text",
      "sub": "English subtitle",
      "animation": "normal_talk",
      "pos": "center",
      "scale": 1.0,
      "text_size": "big"
    }
  ]
}
```

**Positions:** center, center-high, center-low, left, right, left-high, right-high, left-low, right-low

**Text sizes:** small, normal, big, huge

**Emotion auto-detection:** text ending with `!!` → excited; `..` → subdued; repeated syllables → lower repetition penalty

---

## Content Direction

- Language: **Korean** (primary), English subtitles
- Vibe: cute, expressive, relatable, meme-friendly, slightly dramatic
- Text: short and punchy — character carries the emotion
- No emoji in Korean text (Jua font doesn't support emoji)
- Watermark: `assets/sprites/watermark.png` at bottom center

See `docs/CONTENT.md` for content categories and ideas.
