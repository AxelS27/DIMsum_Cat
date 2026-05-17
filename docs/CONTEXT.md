# DIMsum Cat — Project Context

> Kawaii animated cat character for short-form Korean content.

## Character

- Name: **DIMsum Cat**
- Gender: female (she/her)
- Personality: cute, expressive, relatable, slightly dramatic
- Handle: `@dimsumcat.studio`

## Platforms

Instagram Reels · TikTok · YouTube Shorts — vertical 1080×1920, 24fps

## Tech Stack

| Component | Detail |
|-----------|--------|
| Renderer | `video_generator.py` (entry point) → `src/` package |
| TTS | GPT-SoVITS local server at `http://127.0.0.1:9880` |
| Voice ref | `assets/audio_reference/dimsum_cat_korean.mp3` |
| Font | Jua-Regular (Korean, cute rounded) |
| Output | `content/<name>/video.mp4` |

## Quick Start

```bash
# 1. Start GPT-SoVITS
D:/GPT-SoVITS/runtime/python.exe D:/GPT-SoVITS/api_v2.py -a 127.0.0.1 -p 9880

# 2. Render a story
.venv/Scripts/python video_generator.py --story content/story_crush
```

## Project Structure

```
assets/
  audio_reference/        ← voice ref audio (gitignored)
  fonts/                  ← Jua-Regular.ttf
  music/                  ← background music tracks
  sprites/
    watermark.png
    dimsum_cat/
      animations/         ← 60 animation folders (frame_a–d.png)
      design/             ← original design sheets

content/
  _template/story.json    ← template for new stories
  <story_name>/
    story.json            ← story config
    video.mp4             ← output (gitignored)
    frames/               ← temp render frames (gitignored)

docs/
  CONTEXT.md              ← this file
  CONTENT.md              ← content categories & ideas
  PLAYBOOK.md             ← rules for AI story generation

scripts/
  extract_sprites.py

src/
  models.py · utils.py · sprite.py
  renderer.py · tts.py · output.py · story.py

video_generator.py        ← 3-line entry point
.env                      ← API keys (gitignored)
```

## Animation Library (60 animations)

**Original 12:** normal_talk, excited_talk, whisper_secret, wink, blow_kiss, heart_eyes, shy_blush, finger_heart, smirk, holding_phone, waiting_reply, got_a_text

**Extended 48:** crying, angry_pout, sleepy_yawn, shocked, confused_thinking, laughing_hard, embarrassed, panic, dizzy, sick_fever, determined, mischief_grin, facepalm, pleading, proud, nervous_sweat, peekaboo, cheering, hugging_pillow, thumbs_up, clapping, salute, need_a_hug, sassy_pose, sulking, begging, sniffling, startled_jump, want_attention, self_hug, side_eye, tiny_tantrum, cozy_blanket, stretching, tongue_out_tease, happy_wiggle, head_tilt, little_wave, curious_peek, daydreaming, rubbing_eyes, tiny_giggle, happy_bounce, listening_closely, tiny_stretch_sit, blow_air_hmph, peek_from_box, mini_twirl

## Content Categories

See `docs/CONTENT.md` for full ideas list.
See `docs/PLAYBOOK.md` to generate a new story with AI.
