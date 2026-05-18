# Bowing Animation Prompts — DIMsum Cat
# Learn Korean: Levels of Apology

> Attach the character reference image when generating each prompt.
> Generate each frame separately, 1:1 ratio, bright green (#00FF00) solid background.
> Save to: `assets/sprites/dimsum_cat/animations/<animation_name>/frame_a.png` etc.

---

## Level Map

| Level | Korean | Romaji | Bow Angle | Animation Name | Sprite Needed? |
|-------|--------|--------|-----------|----------------|----------------|
| 1 | 미안 | mi-an | no bow, sheepish | `embarrassed` (reuse existing) | ❌ |
| 2 | 미안해 | mi-an-hae | head nod ~5° | `bow_nod` | ✅ |
| 3 | 미안해요 | mi-an-hae-yo | polite bow ~20° | `bow_polite` | ✅ |
| 4 | 죄송해요 | joe-song-hae-yo | waist bow ~45° | `bow_medium` | ✅ |
| 5 | 죄송합니다 | joe-song-ham-ni-da | deep bow ~70° | `bow_formal` | ✅ |
| 6 | 정말 죄송합니다 | jeong-mal joe-song-ham-ni-da | near 90° | `bow_deep` | ✅ |
| 7 | 백배사죄합니다 | baek-bae sa-joe ham-ni-da | prostrate on floor | `bow_prostrate` | ✅ |

---

## `bow_nod` — 미안해 (head nod, ~5°)

**Frame A** — standing, casual guilty look, one hand scratching back of head
```
[character ref] standing upright, one hand raised scratching back of head, casual sheepish guilty grin, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame B** — head dips forward ~5°, eyes half closed
```
[character ref] standing upright, head slightly tilted forward in a tiny apologetic nod, eyes half-closed, soft sorry expression, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame C** — head nod peak, eyes closed, small nervous smile, slight blush
```
[character ref] standing upright, head nodded down 5 degrees, eyes shut, small apologetic smile, slight blush, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame D** — same as Frame A (head back up, sheepish grin)

---

## `bow_polite` — 미안해요 (~20° bow)

**Frame A** — standing, shy expression, hands clasped in front of chest
```
[character ref] standing upright, hands clasped together in front of chest, shy apologetic smile, slight blush, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame B** — body tilting forward ~10°, eyes starting to close
```
[character ref] body tilted forward 10 degrees at the waist, beginning a polite bow, eyes half-closed, arms sliding to sides, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame C** — peak bow ~20°, eyes closed, gentle smile
```
[character ref] body bent forward 20 degrees at the waist, polite bow pose, eyes closed, arms straight at sides, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame D** — same as Frame A (returned upright, relieved smile)

---

## `bow_medium` — 죄송해요 (~45° bow)

**Frame A** — standing, worried expression, hands pressed together (prayer-like)
```
[character ref] standing upright, hands pressed together prayer-like in front, worried apologetic expression, eyebrows slightly furrowed, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame B** — body forward ~25°, head down, arms dropping to sides
```
[character ref] body bent forward 25 degrees at the waist, head lowered, arms starting to hang at sides, sincere apology bow mid-motion, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame C** — peak bow ~45°, eyes closed, arms straight down
```
[character ref] body bent forward 45 degrees at the waist, eyes tightly closed, arms straight down along body, sincere medium bow, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame D** — same as Frame B (rising back up ~25°)

---

## `bow_formal` — 죄송합니다 (~70° bow)

**Frame A** — standing stiff and straight, very serious/guilty face, arms rigid at sides
```
[character ref] standing perfectly upright, very serious guilty expression, arms stiff straight at sides, tense formal posture, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame B** — body forward ~40°, head down, eyes closed
```
[character ref] body bent forward 40 degrees at the waist, head lowered eyes closed, arms straight down, formal bow in motion, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame C** — peak bow ~70°, back nearly flat, head very low, eyes shut tight
```
[character ref] deep formal bow, body bent 70 degrees forward at the waist, back nearly horizontal, head very low, eyes shut tight, arms straight down, very formal apology pose, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame D** — same as Frame B (rising back up)

---

## `bow_deep` — 정말 죄송합니다 (~90° bow)

**Frame A** — standing, trembling, teary eyes, hands clasped tightly
```
[character ref] standing upright, large teary eyes, hands clasped tightly together, trembling apologetic expression, sweat drop, very remorseful look, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame B** — body forward ~55°, intense apology mid-motion
```
[character ref] body bent forward 55 degrees at the waist, head down, arms straight down, intense apology bow mid-motion, strained expression, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame C** — peak 90° bow, back fully horizontal, head parallel to ground
```
[character ref] full 90 degree bow, back completely horizontal, head parallel to the floor, arms hanging straight down, maximum standing bow position, very sincere deep apology, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame D** — same as Frame B (slowly rising)

---

## `bow_prostrate` — 백배사죄합니다 (full floor bow 큰절)

**Frame A** — standing, dramatic streaming tears, arms reaching forward in preparation
```
[character ref] standing upright, dramatic teary streaming eyes, arms stretched slightly forward in preparation for prostration, ultra-remorseful desperate expression, bright green background, chibi sprite style, full body centered --ar 1:1
```

**Frame B** — dropping to knees, upper body plunging forward, arms reaching floor
```
[character ref] on knees, upper body bent 90 degrees forward, arms stretched reaching toward the floor, mid-drop into a full prostrate bow, bright green background, chibi sprite style, full body visible --ar 1:1
```

**Frame C** — fully flat, forehead on ground, bottom slightly raised (큰절)
```
[character ref] fully prostrate on the floor, forehead touching the ground, arms stretched flat forward on the ground, bottom slightly raised, traditional Korean full bow (keunjeol) pose, side-angle view, bright green background, chibi sprite style, full body visible --ar 1:1
```

**Frame D** — still on floor, head slightly lifted, one giant teary pleading eye looking up
```
[character ref] still lying prostrate on floor, head barely lifted off the ground, one large teary pleading eye peeking up, desperate hopeful expression, arms still flat forward, bright green background, chibi sprite style, full body visible --ar 1:1
```
