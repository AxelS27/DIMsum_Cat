# DIMsum Cat — Story Generation Playbook

> This file is the rule base for AI-assisted story generation.
> To create a new video: tell the AI what you want, reference this file, and it will generate a complete `story.json` ready to render.

---

## How to Use

Tell the AI agent:
> "Buat story baru untuk DIMsum Cat tentang [topic/idea]. Ikuti rules di PLAYBOOK.md."

The AI will output a complete `story.json` you can save to `content/<name>/story.json` and render.

---

## Character Rules

- DIMsum Cat is a **cute kawaii cat girl**, pronoun **she/her**
- She is expressive, relatable, slightly dramatic, and very Korean
- Her "voice" is young, bubbly, and emotionally reactive
- Main text is always in **Korean** (hangul)
- Subtitles are always in **English**
- Never use emoji inside the `text` field (Jua font doesn't support it)
- Emoji is OK in `sub` and `description`

---

## Story Structure Rules

### Timing
- Total video: **15–25 seconds** for stories, **10–20 seconds** for POV/tutorial
- First beat always starts at `0.0`
- Gap between beats: **2.5–4 seconds** (auto-retimed by TTS, but set sensible defaults)
- Last beat: leave ~2s before end of `duration`

### Beat Count
- Story/K-Drama: **6–9 beats**
- POV: **4–6 beats**
- Tutorial: **4–7 beats**
- K-pop: **3–5 beats** (minimal text, let music carry it)

### Beat Writing Rules
- `text`: short, punchy Korean — **max 10 characters** per line
- `sub`: English translation or context — **max 40 characters**
- Build emotional arc: setup → escalation → reaction → resolution/punchline
- End on a strong beat (cheering, determined, blow_kiss, side_eye, etc.)
- Silence beats (`.....`) are OK for dramatic pause — use `side_eye` or `sulking`

### Scale & Position
- Big emotional moments: `scale 1.2–1.4`, `text_size: "huge"`
- Normal narrative: `scale 1.0–1.1`, `text_size: "big"`
- Subdued/whisper moments: `scale 0.9–1.0`, `text_size: "normal"`
- Vary position (center/left/right) to add dynamism — don't keep same pos all beats

---

## Content Categories & Templates

### 1. Story (연애 스토리)
Relatable love/crush mini-story from DIMsum Cat's perspective.

```
bg: soft pastel (#f5f0ec, #fdf0f5, #f0f5fd)
tts: true
bg_music: ../../assets/music/love_maybe.mp3
arc: daily moment → excited → twist/disappointment → reaction → resolve
```

Example beat flow:
1. Setup (normal_talk, center, big)
2. Exciting moment (want_attention / excited_talk, center, huge + scale 1.25)
3. Feeling (happy_wiggle / shy_blush, center-high, normal)
4. Twist (whisper_secret, right, normal + scale 0.95)
5. Disappointment (embarrassed / crying, left, normal)
6. Silence/reaction (side_eye, center-low, huge)
7. Resolve (determined, center, big)
8. Punchline ending (cheering / blow_kiss, center, huge + scale 1.3)

---

### 2. POV (POV 시리즈)
DIMsum Cat acts out a relatable scenario. Text sets up the POV, beats escalate.

```
bg: slightly darker pastel (#ede8f5, #f5ede8)
tts: true
bg_music: any lo-fi/soft track
first beat text: "POV:" + scenario in Korean
```

Example beat flow:
1. POV setup (normal_talk, center, big)
2. Initial reaction (shocked / startled_jump, center, huge)
3. Escalation (nervous_sweat / panic, center-high, normal)
4. Peak reaction (tiny_tantrum / laughing_hard, center, huge + scale 1.3)
5. Resolution/punchline (side_eye / mischief_grin, center-low, huge)

---

### 3. K-pop (케이팝 시리즈)
DIMsum Cat vibes to viral K-pop moments. Music IS the content.

```
bg: vibrant pastel (#f5f0ff, #fff0f5)
tts: false
bg_music: path to the K-pop track
duration: match to the viral 10–15 second clip
```

Beat rules:
- Minimal text — just Korean fangirl reactions ("언니!!", "이 파트!!!", "너무 좋아!!")
- Time beats to the drop/chorus of the song
- Use high-energy animations on the beat drop
- End with finger_heart or blow_kiss

---

### 4. Korean Tutorial (한국어 배우기)
Teach one Korean word or phrase per video.

```
bg: soft warm (#f5f2ee, #fef9f0)
tts: true
bg_music: gentle lo-fi
```

Example beat flow:
1. Hook question (normal_talk, center, big) — "이 단어 알아?"
2. Show the word (center, huge, scale 1.3) — large Korean word
3. Pronunciation hint in sub (head_tilt / curious_peek)
4. Meaning reveal (wink / finger_heart, center, big)
5. Example sentence (whisper_secret / normal_talk, right, normal)
6. Reaction / use in context (excited_talk / shy_blush, center, big)
7. Closing (blow_kiss / cheering, center, huge)

---

### 5. K-Drama Recreate (드라마 재현)
DIMsum Cat acts out an iconic scene from a Korean drama.

```
bg: match drama mood (warm for romance, cool for tense)
tts: true
bg_music: drama OST or emotional ballad
first beat sub: "[Drama Title] — [scene context]"
```

Beat rules:
- Open with drama title as subtitle context
- Keep dialogue faithful but short (max 8 Korean chars per beat)
- Build to the most iconic line of the scene
- End on the emotional peak beat
- Use OST as bg_music for instant recognition

---

## Available Positions
```
center · center-high · center-low
left · right
left-high · right-high · left-low · right-low
```

## Available Text Sizes
```
small · normal · big · huge
```

## Emotion Auto-Detection (TTS)
The TTS system auto-adjusts delivery based on text:
- Ends with `!!` → excited, faster delivery
- Ends with `..` or `…` → subdued, slower
- Repeated syllables (두근두근) → lower repetition penalty
- Override per beat with `"tts_speed"` and `"tts_temperature"`

---

## Output File Template

Save as `content/<story_name>/story.json`:

```json
{
  "title": "English title for video metadata",
  "description": "YOUR CAPTION HERE\n\n#crush #firstlove #kawaii #dimsumcat #fyp #foryou #viral #anime #kpop #cdrama #kdrama #romance #coquette #blowthisup #xyzbca #trending #pov #storytime #thatgirl #softlife",

  "animation": "normal_talk",
  "bg": "#f5f0ec",

  "tts": true,
  "gpt_sovits_ref": "../../assets/audio_reference/dimsum_cat_korean.mp3",
  "gpt_sovits_server": "http://127.0.0.1:9880",
  "gpt_sovits_speed": 0.88,

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

---

## Checklist Before Rendering

- [ ] All `text` fields are Korean hangul
- [ ] All `sub` fields are English
- [ ] No emoji in `text` fields
- [ ] `duration` is set (or remove it to let TTS auto-calculate)
- [ ] `gpt_sovits_ref` path is correct
- [ ] `bg_music` path is correct
- [ ] Story folder created at `content/<name>/`
- [ ] GPT-SoVITS server is running
