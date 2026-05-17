# DIMsum Cat - Project Context

> Short-form kawaii animation content using the DIMsum Cat sprite animation pack.

## Project Summary

DIMsum Cat is a cute animated cat character brand for short-form social videos. The current direction is to create content similar to `docs/video_example.mp4`: simple, expressive, loop-friendly character animation with playful text, reactions, and lightweight storytelling.

Primary channel handle:

- Instagram: `@dimsumcat.studio`

Primary platforms:

- Instagram Reels
- TikTok
- YouTube Shorts

## Current Asset Status

The current character system is no longer modular head/body/effect composition. It now uses ready-to-animate full-frame sprites extracted from:

- `design.png`
- `characters/dimsum_cat/design/design.png`

Extracted animation frames are stored in:

```text
characters/dimsum_cat/
+-- design/
|   +-- design.png
+-- animations/
|   +-- normal_talk/
|   +-- excited_talk/
|   +-- whisper_secret/
|   +-- wink/
|   +-- blow_kiss/
|   +-- heart_eyes/
|   +-- shy_blush/
|   +-- finger_heart/
|   +-- smirk/
|   +-- holding_phone/
|   +-- waiting_reply/
|   +-- got_a_text/
+-- preview/
```

Each animation folder contains four anchored PNG frames:

```text
frame_a.png
frame_b.png
frame_c.png
frame_d.png
```

Important implementation note:

- Frames inside the same animation must keep the same canvas size.
- Do not tight-trim each frame independently, because that causes visible jitter in loops.
- Some animations need extra safe area for effects, especially `blow_kiss` hearts.

## Animation Pack

The current DIMsum Cat sprite pack contains 12 short loop animations:

| Animation | Use Case |
|---|---|
| `normal_talk` | default talking / explaining |
| `excited_talk` | energetic speaking, announcements |
| `whisper_secret` | secret tips, flirty lines, suspense |
| `wink` | playful punchline or flirt beat |
| `blow_kiss` | romantic/flirty ending |
| `heart_eyes` | love, obsession, cute reaction |
| `shy_blush` | embarrassment, confession, compliment reaction |
| `finger_heart` | cute call-to-action, love phrase |
| `smirk` | cheeky joke, confident line |
| `holding_phone` | texting setup |
| `waiting_reply` | waiting for chat response |
| `got_a_text` | notification / reply moment |

Generated previews:

```text
characters/dimsum_cat/preview/cropped_animation_frames_contact.png
characters/dimsum_cat/preview/all_animations_loop.gif
characters/dimsum_cat/preview/gifs/
```

## Content Direction

The content should feel:

- cute
- flirty
- lightweight
- expressive
- meme-friendly
- easy to understand without long explanations

Core content ideas:

- Mandarin flirting phrases
- texting and relationship mini-scenes
- cute reaction loops
- short romantic comedy beats
- language-learning moments with simple captions

The character should carry most of the emotional tone. Text should be short and readable.

## Video Format

Recommended base format:

- Vertical 9:16
- 720x1280 or 1080x1920
- 5-15 seconds for simple phrase videos
- 10-30 seconds for mini-story videos
- loop-friendly endings where possible

Visual structure:

```text
Top: short hook or Mandarin phrase
Middle: DIMsum Cat animation
Below/near cat: translation, pinyin, or chat bubble
Bottom: watermark @dimsumcat.studio
```

## Example Video Style

Use `docs/video_example.mp4` as the style reference for pacing and presentation. The final video should have:

- animated character frames, not static slides
- readable text overlays
- cute timing and simple motion
- minimal clutter
- soft/pastel styling
- subtle camera movement where useful
- watermark or handle placement

## Production Pipeline

Current practical pipeline:

1. Pick one content idea or phrase.
2. Select one DIMsum Cat animation folder.
3. Loop or sequence its four PNG frames.
4. Composite into a vertical canvas.
5. Add text overlays, subtitles, and watermark.
6. Add simple motion polish: pop, bounce, zoom, shake, or fade.
7. Export as MP4/GIF preview.

Recommended source folders:

```text
characters/dimsum_cat/animations/<animation_name>/frame_a.png
characters/dimsum_cat/animations/<animation_name>/frame_b.png
characters/dimsum_cat/animations/<animation_name>/frame_c.png
characters/dimsum_cat/animations/<animation_name>/frame_d.png
```

## Technical Notes

Animation:

- Use anchored frame canvases per animation.
- Preserve transparent PNGs.
- Avoid per-frame auto-cropping after extraction.
- Use consistent frame duration for simple loops, around 150-220 ms per frame.

Rendering:

- Python + Pillow is enough for frame composition.
- FFmpeg is preferred for MP4 export when available.
- GIF output is acceptable for quick QA previews.

Text:

- Keep captions short.
- Use large readable text for mobile.
- Avoid covering the cat's face.
- Keep watermark visible but not distracting.

## File Structure Target

```text
project/
+-- docs/
|   +-- CONTEXT.md
|   +-- video_example.mp4
+-- characters/
|   +-- dimsum_cat/
|       +-- design/
|       |   +-- design.png
|       +-- animations/
|       |   +-- <animation_name>/
|       |       +-- frame_a.png
|       |       +-- frame_b.png
|       |       +-- frame_c.png
|       |       +-- frame_d.png
|       +-- preview/
+-- output/
+-- video_generator.py
```

## Next Steps

- Build a video generator that can render one short vertical video from a chosen animation.
- Use `@dimsumcat.studio` as the watermark.
- Start with one simple phrase/reaction video before expanding into batch generation.
- Keep the pipeline compatible with the current anchored four-frame animation folders.
