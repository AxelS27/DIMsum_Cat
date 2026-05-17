# DIMsum Cat — Story Generation Playbook

> Rule base for AI-assisted story generation.
> To create a new video: tell the AI your idea, reference this file, and it will output a complete `story.json` ready to render.

---

## How to Use

Tell the AI agent:
> "Buat story baru untuk DIMsum Cat tentang [topic/idea]. Ikuti rules di docs/PLAYBOOK.md."

### AI Generation Flow

1. **Identify the character** being used (default: `dimsum_cat`; others may be added later)
2. **Check available animations** by listing the character's animations folder:
   `assets/sprites/<character_name>/animations/`
   → Do NOT rely on any hardcoded animation list. Always read the actual folder. New animations may have been added.
3. **Read** `content/_template/story.json` as the base
4. **Copy** the template structure — do not start from scratch
5. **Fill in** all fields based on the idea and rules below, picking animations from what actually exists in step 2
6. **Output** the completed `story.json`

The user saves it to `content/<name>/story.json` and renders with:
```bash
.venv/Scripts/python video_generator.py --story content/<name>
```

---

## Characters

Characters live in `assets/sprites/<character_name>/`. More characters will be added over time.

### Active Characters

| Folder | Name | Personality | Voice Ref |
|--------|------|-------------|-----------|
| `dimsum_cat` | DIMsum Cat | cute kawaii cat girl, she/her, expressive, slightly dramatic | `assets/audio_reference/dimsum_cat_korean.mp3` |

> When a new character is added, update this table. Each character has its own animations folder and voice reference audio.

### Universal Character Rules
- Main `text` is always **Korean hangul**
- `sub` is always **English**
- **Never use emoji in `text`** (Jua font doesn't support it)
- Emoji OK in `sub` and `description`

### Animations — ALWAYS Check the Folder

**Do not use any hardcoded animation list.** Always list the actual folder:
```
assets/sprites/<character_name>/animations/
```
New animations may be added at any time. Pick the ones that best fit the emotion of each beat from what actually exists. Use `--list-animations` CLI flag to see all available animations:
```bash
.venv/Scripts/python video_generator.py --list-animations
```

---

## Hashtag System

### Master Hashtags (used in ALL videos)
```
#dimsumcat #kawaii #fyp #foryou #viral #kpop #kdrama #cdrama #anime #cute #blowthisup #xyzbca #trending #coquette #softlife
```

### Per-Category Hashtags (add on top of master)

| Category | Extra Hashtags |
|----------|---------------|
| Story | `#crush #firstlove #schoolcrush #lovestory #romance #relatable #storytime` |
| POV | `#pov #povstory #scenario #relatable #storytime` |
| K-pop | `#kpop #kpopfyp #newjeans #aespa #ive #bts #stayc #kpopcover #kpopdance` |
| Tutorial | `#learnkorean #korean101 #koreanwords #studykorean #hangul #koreanculture` |
| K-Drama | `#kdrama #koreandrama #dramarecap #kdramaclip #dramaOST #goblin #cloy #queentears` |

### Description Format
```
[Your caption here] 🐱

[Master hashtags] [Category hashtags]
```

---

## Background Color Rules

Background color (`bg`) should always **match the mood of the video** — not locked to a category. Use this as a guide:

| Mood | Color | Hex |
|------|-------|-----|
| Warm & romantic | Soft peach | `#f5f0ec` |
| Dreamy / crush | Blush pink | `#fdf0f5` |
| Calm & gentle | Baby blue | `#f0f5fd` |
| Cozy / nostalgic | Warm cream | `#fef9f0` |
| Hype / energetic | Soft lavender | `#f5f0ff` |
| Tense / dramatic | Cool blue-grey | `#e8edf5` |
| Sad / emotional | Muted lilac | `#ede8f5` |
| Cheerful / playful | Mint green | `#f0fdf5` |
| Bold / confident | Pale rose | `#fff0f5` |

**Rule:** Pick the color that fits the *emotion of the story*, not the category. A POV video can be warm peach if it's romantic. A K-Drama recreate can be cool blue if it's a tense scene.

---

## Story Structure Rules

### Timing
- Total video: **15–25s** for Story/K-Drama, **10–20s** for POV/Tutorial/K-pop
- First beat at `0.0`
- Beat gaps: **2.5–4s** (auto-retimed by TTS)
- Last beat: ~2s before `duration` end

### Beat Count
- Story / K-Drama: **6–9 beats**
- POV: **4–6 beats**
- Tutorial: **4–7 beats**
- K-pop: **4–7 beats** (TTS sings/reacts along with music)

### Beat Writing Rules
- `text`: short Korean — **max 10 chars per line**
- `sub`: English context — **max 40 chars**
- Arc: setup → escalation → reaction → resolution/punchline
- End on a strong beat
- Silent dramatic pause: `"text": "...."` with `side_eye` or `sulking`

### Scale & Position
- Big moment: `scale 1.2–1.4`, `text_size: "huge"`
- Normal: `scale 1.0–1.1`, `text_size: "big"`
- Whisper/subdued: `scale 0.9–1.0`, `text_size: "normal"`
- Vary `pos` between beats for dynamism

---

## Content Categories

### 1. Story (연애 스토리)
Relatable love/crush mini-story.

```
bg: match mood (see Background Color Rules)
tts: true
bg_music: ../../assets/music/love_maybe.mp3
description: caption + master # + story #
```

Beat flow: Setup → Excited moment → Feeling → Twist → Disappointment → Silence → Resolve → Punchline

Suggested animation mood: expressive talking, excitement, embarrassment, side-eye, determination, cheering — check folder for actual names

---

### 2. POV (POV 시리즈)
Relatable scenario. First beat opens with "POV:" in Korean.

```
bg: match mood (see Background Color Rules)
tts: true
bg_music: lo-fi track
first beat text: "POV:" + scenario
description: caption + master # + pov #
```

Beat flow: POV setup → Reaction → Escalation → Peak → Punchline

Suggested animation mood: shock, panic, escalating reaction, punchline — check folder for actual names

---

### 3. K-pop (케이팝 시리즈)
DIMsum Cat **sings along** to the viral K-pop moment with TTS voice + reacts with animations.

```
bg: match mood (see Background Color Rules)
tts: true
bg_music: path to K-pop track (TTS voice sings over the music)
gpt_sovits_speed: 1.0 (match song tempo)
description: caption + master # + kpop #
```

Beat rules:
- `text` = Korean lyrics of the viral part (phonetically or actual lyrics)
- `sub` = English lyric translation
- Time beats tightly to the song's rhythm
- High-energy animations on the drop: mini_twirl, happy_bounce, cheering, clapping
- End with finger_heart or blow_kiss
- Use `tts_speed: 1.05–1.15` on chorus beats to match song energy

---

### 4. Korean Tutorial (한국어 배우기)
One Korean word or phrase per video.

```
bg: match mood (see Background Color Rules)
tts: true
bg_music: gentle lo-fi
description: caption + master # + tutorial #
```

Beat flow: Hook ("이 단어 알아?") → Show word → Pronunciation → Meaning reveal → Example sentence → Use in context → Closing

Suggested animation mood: curious, explaining, listening, cute reveal, closing — check folder for actual names

---

### 5. K-Drama Recreate (드라마 재현)
Iconic scene from a Korean drama, acted out by DIMsum Cat.

```
bg: match mood (see Background Color Rules)
tts: true
bg_music: drama OST
first beat sub: "[Drama Title] — [scene context]"
description: caption + master # + kdrama #
```

Beat rules:
- Keep dialogue short (max 8 Korean chars per beat)
- Build to the most iconic line
- End on emotional peak
- Use OST as bg_music for instant fan recognition

Suggested animation mood: romantic, shy, emotional peak, dramatic — check folder for actual names

---

## Available Positions
```
center · center-high · center-low
left · right · left-high · right-high · left-low · right-low
```

## Available Text Sizes
```
small · normal · big · huge
```

## TTS Emotion Auto-Detection
- Ends `!!` → excited, faster
- Ends `..` → subdued, slower
- Repeated syllables (두근두근) → lower repetition penalty
- Manual override: `"tts_speed"` and `"tts_temperature"` per beat

---

## Output Template

Save as `content/<name>/story.json`:

```json
{
  "title": "English title",
  "description": "Your caption 🐱\n\n#dimsumcat #kawaii #fyp #foryou #viral #kpop #kdrama #cdrama #anime #cute #blowthisup #xyzbca #trending #coquette #softlife\n[category hashtags here]",

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

## Pre-Render Checklist

- [ ] All `text` fields are Korean hangul
- [ ] All `sub` fields are English
- [ ] No emoji in `text`
- [ ] Description has master # + category #
- [ ] `gpt_sovits_ref` path exists
- [ ] `bg_music` path exists
- [ ] GPT-SoVITS server is running at port 9880
- [ ] Story folder created at `content/<name>/`
