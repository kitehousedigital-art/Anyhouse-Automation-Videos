# MCP reference - `anyhouse-video-studio`

Transport: stdio. Python 3.9+, `pip install -r requirements.txt` (needs `mcp>=1.2,<2`, Pillow; FFmpeg via PATH or `imageio-ffmpeg`).

## Connect it
**Claude Code** - the repo ships `.mcp.json`; open the folder in Claude Code and approve the server. Or:
```bash
claude mcp add anyhouse-video-studio -- python mcp_server/anyhouse_mcp.py
```
**Claude Desktop** - add to `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\`; macOS: `~/Library/Application Support/Claude/`), use absolute paths:
```json
{ "mcpServers": { "anyhouse-video-studio": {
    "command": "python",
    "args": ["C:\\Users\\ME\\Desktop\\Anyhouse-Automation-Videos\\mcp_server\\anyhouse_mcp.py"] } } }
```
(see `examples/claude_desktop_config.json`). Restart Claude Desktop. If `python` is not on PATH use the full path to python.exe.
**Any other MCP client**: command `python`, args `[mcp_server/anyhouse_mcp.py]`, working directory = repo root.

Give the agent the playbook: load `skills/anyhouse-video-studio/SKILL.md` as a skill (Claude) or point the agent at the resource `studio://guide`.

## Tools (23)
| Tool | Purpose |
|---|---|
| `studio_info` | canvas, counts, FFmpeg, clips, renders, guide pointers - call first |
| `list_videos` / `get_video` | compact list / full JSON of a video |
| `describe_video` | engine's real timeline: total length, per-element start/end/font px/box, background |
| `list_layouts` / `get_layout` | layouts (modes together/stack/single) and full JSON |
| `list_styles` | Instagram-style presets + font mapping + font files |
| `list_backgrounds` / `add_background` | clips in `inbox/`; copy a local video in |
| `list_renders` | MP4s and exported covers |
| `preview_frame` | one still frame **as an image** (fast, no FFmpeg render) |
| `export_cover` | full-res 1080x1920 PNG to `output/covers/` (with or without text) |
| `upsert_video` / `update_video` / `delete_video` / `duplicate_video` | manage content (validated, atomic) |
| `style_element` | preset and/or override keys on `header`, `line:N`, `lines`, `all`; or clear |
| `upsert_layout` / `delete_layout` / `set_layout_style` | manage layouts; apply a preset to a layout block |
| `import_sheet` | Google Sheet / CSV -> videos (dry-run first; column auto-mapping) |
| `render_videos` | render MP4s (`draft`/`standard`/`high`), wait with progress or fire-and-forget |
| `render_status` | poll background renders |

Resources: `studio://guide` (playbook), `studio://schema` (field reference), `studio://extending` (developer guide).
Prompt: `make_videos(topic, count, audience)`.

## Behaviour notes
- Tools validate input and return readable errors (unknown layout, bad element, unknown style keys) - fix and retry.
- `preview_frame` returns an image content block - models with vision can inspect layout, fit and contrast.
- Writes are atomic and the web UI auto-reloads (within ~4 s) if it has no unsaved edits.
- `render_videos` needs >= 1 clip in `inbox/` and FFmpeg; two videos render in parallel.
- The server never calls the network except `import_sheet` (Google) - all rendering is local.
