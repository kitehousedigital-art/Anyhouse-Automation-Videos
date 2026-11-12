---
name: anyhouse-video-studio
description: Create, style, preview and render vertical (1080x1920) text-overlay videos and cover images for faceless social channels (Instagram Reels / Stories, TikTok, Shorts) with the AnyHouse Video Studio MCP. Use for writing video content, choosing layouts and Instagram-style fonts, importing rows from Google Sheets, previewing frames, exporting cover images and rendering MP4s.
---

# AnyHouse Video Studio - agent playbook

You drive a local video tool through the **anyhouse-video-studio MCP**. It overlays auto-fitting text (a headline plus
lines that appear every 1-3 s) on background clips and renders 1080x1920 MP4s. No AI runs at render time: you write the
content and style, the engine does the layout and encoding. A human may have the web UI open on the same project -
it reloads by itself when you change files.

**Client context (default):** AnyHouse.me - AI rental search for renters in the EU / Netherlands. Tone: energetic, direct,
useful, no fluff. Audience: expats, students, people moving cities. Change this section if the project serves another brand.

## 0. Before you start (30 seconds)
1. `studio_info` - check `ffmpeg: true` and that `background_clips` is not empty (renders need >= 1 clip; previews do not).
2. `list_layouts`, `list_styles`, `list_videos` - know what exists before creating anything. Reuse ids; never duplicate a topic.
3. Read `references/schema.md` (field reference) when you need a key you do not remember. It is also the MCP resource `studio://schema`.

## 1. The model in one screen
- **Video** = `{id, template (layout id), header, lines[], header_style?, interval?, hold?, tags?, background?, cta?, status?, caption?, hashtags?}`.
- **Line** = a string, or an object `{text, color, size, font, align, upper, stroke, bg_mode, bg_color, shadow_on, glow_color, opacity, rotate, dx, dy, anim, delay, show, ...}` for per-line styling.
- **Layout** (template) = timing mode + header/body style blocks. Modes: `together` (everything at once), `stack` (lines appear one by one and stay), `single` (one line at a time, each replaces the previous).
- **Style preset** = a one-call look (font + color + outline + shadow/glow + box). Instagram text styles are mapped to free lookalike fonts: Classic, Modern, Neon, Typewriter, Strong, Elegant, Directional, Literature, Editor, Bubble, Deco, Poster, Squeeze, Meme, Signature, Rosalia.
- Positions are fractions of 1080x1920; offsets `dx`/`dy` are pixels. A literal line break inside one on-screen line = a newline (or ` | ` in a string).

## 2. Workflow - make a video
1. **Brief** -> one idea, one promise ("5 documents landlords ask for in NL"). If the request is vague, pick the most useful reading and say which in your report; ask only if the topic itself is unclear.
2. **Research** any factual claim (rents, deposits, deadlines, laws, prices) with web search; prefer official / primary sources. Keep the URL. **Never invent numbers.** If you cannot verify, leave the figure out or set `"status": "verify"`.
3. **Write** (see `references/design-guide.md`): hook headline <= 9 words, 3-6 lines, <= 8 words per line (single) or <= 12 (stack/together). Put sources in `caption`, hashtags in `hashtags`.
4. **Pick layout** - lists that build up -> `stack`; step-by-step / punchy statements -> `single`; headline-only or short facts -> `together`.
5. `upsert_video` (id optional). Fix any warnings it returns.
6. **Style** - `style_element` with a preset on `header` and/or `lines`; tweak with `style` keys (color for emphasis, `anim`, `size`). Whole-layout look changes go through `set_layout_style`, not per video.
7. **Check** - `describe_video` (timing, font px, overlaps) then `preview_frame` and *look at the image*: text fits? contrast OK? nothing in the top 13% / bottom 20% / right 11% Reels-UI zones? last line readable for >= 2 s?
8. **Fix** and re-preview (loop until clean; keep it to a few rounds).
9. **Render** - `render_videos([id], quality="draft")` to check motion/timing; `"standard"` for the final. Report the file path.

Batch work: write all videos first, preview each, then render together. Two renders run in parallel.

## 3. Workflow - images (covers, thumbnails, story stills)
- Quick still to *inspect*: `preview_frame(id, t)`.
- Deliverable image: `export_cover(id, t, include_text=True)` -> full-res 1080x1920 PNG in `output/covers/`. `include_text=False` gives the clean darkened background frame for use in a design tool.
- Richer thumbnails (extra graphics, logos, layered type): export the clean frame, then build the design in Canva/Figma if a connector is available - say so rather than faking it.
- Pick `t` when the key line is on screen (use `describe_video` -> element start/end times).

## 4. Workflow - Google Sheet -> videos
1. Ask for / receive the link. It must be shared **Anyone with the link: Viewer** (or published as CSV). Private sheets are not supported.
2. `import_sheet(url, dry_run=true)` -> read `auto_mapping` and `preview`. Wrong columns? pass `mapping={"header":"Hook","lines":"Script"}`.
3. Run again with `dry_run=false` (`duplicates="skip"` unless the user wants updates). Then `preview_frame` a few imported videos; imported text is unstyled - apply a style preset and fix overflow.
4. Imported content is raw: fact-check figures before rendering.

## 5. Style quick reference
| Want | Do |
|---|---|
| Instagram "Strong" look | preset `strong` (shadow) or `strong_yellow` (yellow box) |
| Neon glow | preset `neon_pink` / `neon_cyan`, or `{"glow_color":"#19E3FF","glow_r":22}` |
| Highlight one line | `style_element(id,"line:2",style={"color":"#FFD21F"})` |
| Make a line enter from below | `{"anim":"slide_up"}` (`slide_down`, `slide_left`, `slide_right`, `none`) |
| Appear later / vanish early | `{"delay":0.5}` / `{"show":1.8}` seconds |
| Nudge position | `{"dx":0,"dy":-40}` px (or fix at layout level with `upsert_layout`) |
| Slower / faster pacing | `update_video(id,{"interval":2.5})` seconds per line |
| Dark/light box | `{"bg_mode":"line","bg_color":"#000000","bg_opacity":0.85}` (`row` = one block, `none`) |

## 6. Rules
- **Preview before render, always.** Renders are the slow step.
- **Facts:** every statistic needs a source in the caption or `status: "verify"`. Say what you could not confirm.
- **Contrast:** light text on a dark/busy clip needs shadow, outline or a box. Avoid pure-color text without one.
- **Fit:** the engine shrinks text to fit; if `font_px` in `describe_video` drops below ~44, shorten the line instead.
- **Don't hand-edit** `content/ideas.json` or `templates/templates.json` when the MCP is available - use the tools (they validate and write atomically).
- **Destructive actions** (`delete_video`, `delete_layout`, `delete_render`, overwriting an existing id): only when asked or when you created the thing in this session.
- **Don't render everything** unprompted - ask or render only the videos you made.
- **Fonts:** the Instagram mappings are *lookalikes* (Instagram's font is proprietary). Say "Instagram-style", not "the Instagram font".
- Background clips must be ones the user supplied or has rights to. Do not download stock footage yourself.

## 7. Errors
| Message | Meaning / fix |
|---|---|
| `unknown template` | use an id from `list_layouts` |
| `FFmpeg not found` | `pip install imageio-ffmpeg` (or `winget install Gyan.FFmpeg`), restart the MCP |
| `No background clips` | `add_background(path)` or drop .mp4 into `inbox/` |
| `The sheet is private` / `Google refused access` | sharing must be "Anyone with the link"; or published CSV; or API key |
| preview shows a gradient | no clips yet - fine for layout checks |
| text overlaps / too small | shorten the lines (best), or switch to a `single` layout; forcing a bigger `size` makes overflow worse |

## 8. Report format (end of a run)
Short and scannable: a table of `id | hook | layout | length | status`, the file paths, the sources used (URLs), and an
"open questions / unverified" list. Do not paste JSON.

## 9. Going further
If the user wants a *new capability* (new effect, exporter, tool, automation) switch to developer mode: read `AGENTS.md`
(repo root) and `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`. Extra recipes: `references/recipes.md`.
