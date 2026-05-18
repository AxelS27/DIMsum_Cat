# DIMsum Cat — Agent & Pipeline Notes

## GPU Requirement

**All heavy processing MUST use GPU (CUDA).** The machine has an NVIDIA GeForce RTX 4060 Laptop GPU.

- PyTorch must be installed with CUDA support: `torch==2.6.0+cu124` (NOT the `+cpu` variant)
- Verify before any upscaling task: `python -c "import torch; print(torch.cuda.is_available())"`
- If CUDA shows `False`, reinstall: `pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124 --force-reinstall --no-deps`
- Scripts that use ESRGAN (gridder, upscale_sprites, process_background) all auto-detect CUDA — no manual flag needed

## TTS Server

GPT-SoVITS runs as a local API server on `http://127.0.0.1:9880`.

- **Start it** from the project root: `.\start_tts.ps1`
- Installed at: `D:\GPT-SoVITS`
- Wait for the server to be ready before rendering with TTS
- Check status: `Invoke-WebRequest -Uri http://127.0.0.1:9880/tts -Method GET`

## Rendering Pipeline

```
story.json → video_generator.py → video.mp4 (with TTS + BGM)
```

- Start TTS server first if `"tts": true` in story.json
- Render: `.venv\Scripts\python video_generator.py --story content/<category>/<name>`
- Output: `content/<category>/<name>/video.mp4`

## Sprite Pipeline (Gridder)

```
design PNG → scripts/gridder → crop → ESRGAN 4x (GPU) → remove_bg → animations/
```

- Config files: `scripts/gridder/configs/<design_stem>.json`
- For designs spanning full width (no left/right panel split): add `"wide_cols": [x1, x2, ...]` to config
- Output goes to `assets/sprites/<character>/animations/`
- Preview first: `python scripts/gridder <design.png> --preview`

## Characters

| Character | Folder | Notes |
|-----------|--------|-------|
| DIMsum Cat | `assets/sprites/dimsum_cat/` | Main character, she/her |
| Tae-ho | `assets/sprites/taeho/` | Tiger king, always elite roles |

See `docs/PLAYBOOK.md` for full character and story rules.
