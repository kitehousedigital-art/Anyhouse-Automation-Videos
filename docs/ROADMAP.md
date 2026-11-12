# Roadmap / backlog

Ordered by value to a faceless-channel workflow. Each item lists where to start (see `AGENTS.md` for conventions).

## Next up
1. **Plan B agent runner** - one command/prompt: topic -> research (web) -> write -> `import`/`upsert_video` -> style -> preview QA -> render -> report with sources.
   Start: a script or Claude Code slash command that loads the skill and calls the MCP; add a `qa_frame` helper that flags low `font_px`, overlap and Reels-zone intrusion from `describe_video` data.
2. **Timeline export** for the user's editor (open question: CapCut / Premiere / DaVinci?). Start: `engine/export_fcpxml.py` (works for Premiere/DaVinci/Final Cut) reading `build()` layers; each layer PNG -> a clip with start/duration/position, background -> track 1. CapCut: draft JSON (reverse-engineered, fragile) or deliver FCPXML/SRT + PNG sequence.
3. **Emoji & flags** - composite Twemoji (CC-BY 4.0, attribute) PNGs inline; today `EMOJI_RE` strips them.
4. **Audio** - TTS voice-over (local engine or API), background music bed with ducking, optional SFX on line entrance; add `audio` block to a video.
5. **Auto-captions** - word-level timing from the voice-over, caption styles (Instagram-style) as a second text track.

## Soon
- Multi-clip backgrounds (cuts every N seconds, crossfade), clip trimming/looping controls, Ken-Burns zoom.
- Brand kits (per-client colors, fonts, footer, CTA, safe zones) selectable per video; `brand.json` -> `brands/<client>.json`.
- More entrances/exits (pop/scale, typewriter reveal, word-by-word highlight), exit animations, per-line fade length.
- Letter-spacing and italic/underline (needs custom glyph layout in Pillow or Pango/Raqm).
- Contact-sheet QA: render a grid of frames for every video for quick human review.
- Render queue persistence + resume; `watch` mode in the UI.

## Integrations
- Sheets write-back (status, render path) via Apps Script or OAuth; Notion / Airtable / CSV-URL importers using `studio.table_to_videos`.
- Publishing: Buffer/Meta Graph API/YouTube upload from `output/` with `caption` + `hashtags` (needs app review/tokens).
- Canva hand-off for rich thumbnails (clean frame from `export_cover(include_text=False)`).
- Webhook: a small tunnel (cloudflared/ngrok) + `/api/hook` so Apps Script/Zapier can push rows; keep it auth-protected.

## Quality / infra
- Pixel-diff regression tests on `composite_still` for each layout; fixtures with fake fonts.
- Package as an installable app (PyInstaller / pipx) and a one-click Windows installer.
- Localisation of the UI; dark/light theme toggle.

## Known limits today
No audio, no emoji, single background per video, no timeline export, Sheets must be link-shared, Instagram font is a lookalike.
