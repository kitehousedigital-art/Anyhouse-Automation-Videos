# AGENTS.md - guide for AI agents working on this repo

Two different jobs, two different playbooks:

| Job | Read |
|---|---|
| **Use** the studio (write content, style, preview, render) | `skills/anyhouse-video-studio/SKILL.md` (also MCP resource `studio://guide`) |
| **Develop** the studio (add features, fix bugs, new tools) | this file + `docs/ARCHITECTURE.md` + `docs/ROADMAP.md` |

## What this project is
A local, token-free **text-overlay video engine** for faceless social channels. Background clips in `inbox/` + content in
`content/ideas.json` -> 1080x1920 MP4s in `output/`. Three front doors share one data layer:
1. **Web UI** (`engine/server.py` + `ui/index.html`) - an editor-style UI: click/drag text on a live preview, Design tab, presets, Sheets import.
2. **CLI** (`engine/render.py`) - `list | gallery | preview | render | watch`.
3. **MCP server** (`mcp_server/anyhouse_mcp.py`) - 23 tools so an agent can do everything the UI can.
Client: AnyHouse.me (AI rental search, EU/Netherlands). Tone: energetic, direct.

## Ground rules
- **Deterministic at render time.** No AI/network calls inside `render.py`. Agents write content; the engine lays it out. Keep it that way.
- **One data layer.** Files are read/written only through `engine/studio.py` (atomic writes). The UI, server and MCP all use it. Do not add a second code path that writes `ideas.json`/`templates.json`.
- **Python stdlib + Pillow (+ optional imageio-ffmpeg, mcp).** No heavy deps without a reason. Windows is the primary user platform (paths, `run.bat`), Linux/macOS must work too.
- **UI is one self-contained file** (`ui/index.html`, vanilla JS, no build step). Keep it that way; inline SVG icons; dark theme variables at the top.
- **Never `print()` to stdout in code the MCP imports** at runtime paths that run inside the server (stdout is the JSON-RPC channel). Use `quiet()` in the MCP or print to stderr.
- **Backward compatible data.** New element/template keys must be optional; old `ideas.json` must keep rendering identically.
- Positions are fractions of 1080x1920; offsets are px. Don't introduce other units.
- Fonts: only OFL/Apache-licensed fonts in `fonts/` (see `fonts/FONTS.md`). Instagram's own font is proprietary - never add it; map styles to lookalikes in `presets.json`.
- Be honest in docs/UI copy: Instagram-*style*, not "the Instagram font".

## Dev loop
```bash
pip install -r requirements.txt
python engine/server.py                 # http://localhost:8000
python -m unittest discover -s tests    # fast, no FFmpeg needed
python engine/render.py preview --id 01_dutch_rental_terms   # a still PNG
python mcp_server/anyhouse_mcp.py       # stdio MCP (use an MCP client to talk to it)
```
Before you finish a change: unit tests pass; `python -c "import ast,sys;[ast.parse(open(f).read()) for f in sys.argv[1:]]" engine/*.py mcp_server/*.py`;
for UI changes, load the page in a headless browser (Playwright) and check the console is clean; for engine changes render a short clip
(`ffmpeg -f lavfi -i testsrc2=size=720x1280:rate=30:duration=3 inbox/test.mp4`) and look at frames
(`ffmpeg -ss 2 -i output/x.mp4 -frames:v 1 f.png`). **Look at the output** - layout bugs are visual.
Restore `content/ideas.json` / `templates/templates.json` after testing (the UI autosaves).

## Where to change what
| Goal | Touch |
|---|---|
| New per-element visual key (e.g. `underline`) | `engine/render.py` (`item_style`/`draw_items`/`post_fx`) -> `studio.py` `ELEMENT_KEYS`/`VIS` -> `ui/index.html` `renderDesign` field + `fillInsp` defaults -> `references/schema.md` -> test |
| New entrance animation | `ANIM_OFFSET` / `timed()` / the ffmpeg overlay expression in `render_video` and `composite_still`; add to the Design `<select>` and schema docs |
| New layout | `templates/templates.json` (or `upsert_layout`); add a `sample` |
| New Instagram-style preset | `presets.json` `styles[]` (+ `fonts[]` if a new font file); the UI/MCP pick it up automatically |
| New MCP tool | `mcp_server/anyhouse_mcp.py`: thin wrapper over `studio.py`/`render.py`, docstring = the tool description the agent reads (write it carefully), validate input, return small JSON; add to `docs/MCP.md` and a test |
| New data source (Notion, Airtable, RSS...) | like Sheets: fetch -> table -> `studio.table_to_videos` -> `merge_imported`; expose as UI panel + MCP tool |
| New exporter (CapCut/Premiere/DaVinci timeline, SRT) | new module `engine/export_*.py` consuming `render.build()` layers (start/end/pos/img) |
| New render option | `render_video` (keep fast path: cropped PNG overlays, `-itsoffset`, windowed inputs) |

## Gotchas learned the hard way
- Overlays are **cropped** PNGs positioned with `pos`; keep them small or renders get 4x slower.
- Layers are time-windowed with `-itsoffset` + `enable='between(t,..)'`; entrance slides use an overlay x/y expression (`eval=frame`).
- `fit()` shrinks text to the box; `size` overrides pick a fixed size (shrinks only if a word is wider than the box).
- `wrap()` glues `1.`-style tokens to the next word so numbers never wrap alone.
- Emoji are stripped (`EMOJI_RE`) because the fonts lack glyphs; flags/emoji need Twemoji PNG compositing (roadmap).
- The server sends element boxes in the `X-Elements` header of `/api/preview`; the UI overlay depends on it.
- UI autosave writes whole files; the UI polls `/api/mtimes` and reloads when an agent changed files and nothing is unsaved.
- Variable fonts: instantiate a static Bold with `fontTools.varLib.instancer` before shipping (Pillow weight handling is unreliable).
- Sandboxes often block non-package-registry hosts: fonts came from `raw.githubusercontent.com/google/fonts`.

## What you can build on top (see docs/ROADMAP.md for detail)
1. **Plan B agent runner**: topic -> research -> write -> fact-check -> render -> frame QA -> report (use the MCP tools).
2. **Timeline export** for the editor the user prefers (FCPXML / EDL / Premiere XML / CapCut draft) so agents can hand off editable timelines.
3. **Audio**: TTS voice-over, music bed with ducking, auto-captions.
4. **Emoji/flags** via Twemoji; **multi-clip** backgrounds with cuts; **brand kits** per client; **scheduler/poster**.
5. **Sheets write-back** (status/render links) and other sources (Notion, Airtable).
