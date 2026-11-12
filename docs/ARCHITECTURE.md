# Architecture

```
                 +-----------------------------+
 Human --------> |  Web UI  ui/index.html      |  vanilla JS, no build
                 +--------------+--------------+
                                | HTTP (localhost:8000)
                 +--------------v--------------+       +----------------------+
                 |  engine/server.py           |       | mcp_server/          |<--- Agent (Claude, ...)
                 |  stdlib ThreadingHTTPServer |       |  anyhouse_mcp.py     |     stdio MCP
                 +--------------+--------------+       +----------+-----------+
                                |                                  |
                       +--------v----------------------------------v--------+
                       |  engine/studio.py  shared data layer (atomic I/O,  |
                       |  validation, presets, Sheets/CSV import)           |
                       +--------+----------------------------------+--------+
                                |                                  |
        content/ideas.json  templates/templates.json  presets.json  brand.json  fonts/  inbox/  output/
                                |
                       +--------v--------+
                       | engine/render.py|  build() -> layers ; composite_still() ; render_video() (FFmpeg)
                       +-----------------+
```

## Render pipeline (`engine/render.py`)
1. `build(item, tpl, brand)` turns a video + layout into **layers**: `{img (RGBA, cropped), pos, start, end, fin, fout, kind, idx, size, anim}`.
   - `fit()` / `fit_width()` pick font sizes (auto-fit into `box_h`, or fixed `size`), `wrap()` wraps words.
   - `draw_items()` draws boxes (`bg` line/row), shadow, glow, outline, text. `item_style()` merges per-element overrides on the layout block.
   - `post_fx()` applies per-element `opacity` + `rotate`. `timed()` sets entrance animation. Timing modes: together / stack / single.
2. `composite_still(bg_img, layers, t, darken)` - one frame for previews (UI, `preview_frame`, `export_cover`).
3. `render_video(...)` - FFmpeg `filter_complex`: background looped + scaled/cropped + darkened (`lutyuv`), each layer is a PNG input
   (`-itsoffset`, windowed with `-t`), faded with `fade alpha=1`, composited with `overlay=x:y:enable='between(t,..)'`
   (slides use x/y expressions). libx264 presets via `QUALITY`; optional NVENC/QSV/AMF with automatic CPU fallback.

## Data model
See `skills/anyhouse-video-studio/references/schema.md`. Per-element overrides are **flat keys** (`bg_mode`, `shadow_on`, `glow_color`, ...)
so the UI, presets and MCP can patch them without nested merging. `studio.flat_to_template_style` converts a preset to the nested
layout form.

## Web UI
Single file. Top bar (menus open popovers: Videos / Clips / Renders / Sheet), contextual toolbar (selected element), stage (live
preview + click/drag overlay + scrubber), right panel tabs: Content / Design / Layout / Edit layout. State lives in `S`
(`videos`, `templates`, `presets`, ...); `dirty()` -> autosave + history snapshot; `preview()` posts item + template to `/api/preview`
which returns a PNG and `X-Elements` boxes. Undo/redo = JSON snapshots of `{videos, templates}`.

## HTTP API (internal)
`GET /api/state | /api/jobs | /api/mtimes | /api/tpl_thumb | /api/bgthumb`, `GET /fonts/<file>`, `/files/output|inbox/<file>`;
`POST /api/preview | content | templates | settings | render | delete | upload | font_upload | sheet | setup_ffmpeg | open_folder`.
Not a public API - use the MCP for automation.

## MCP server
`FastMCP` (mcp>=1.2,<2) over stdio. Tools are thin wrappers around `studio.py` + `render.py`. stdout is reserved for JSON-RPC; engine
prints are redirected to stderr (`quiet()`). Renders run in a 2-worker thread pool; `render_videos` can wait (with progress) or return
immediately. Resources: `studio://guide`, `studio://schema`, `studio://extending`. Prompt: `make_videos`.

## Concurrency
UI and MCP may both touch the files. Writes are atomic (`os.replace`). The UI reloads when files change and nothing is unsaved; if the
UI has unsaved edits its next save wins - advise the user to save/reload before asking an agent to edit.

## Testing
`tests/` - unit tests that need neither FFmpeg nor a browser (layout build, overrides, presets, sheet mapping, MCP tool functions).
CI runs them on every push. Visual checks (render a frame and look) are part of the dev loop in `AGENTS.md`.
