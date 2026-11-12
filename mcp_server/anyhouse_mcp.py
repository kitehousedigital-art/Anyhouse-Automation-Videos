#!/usr/bin/env python3
"""AnyHouse Video Studio - MCP server (stdio).

Lets an AI agent drive the same project the web UI edits: write video content, pick layouts and Instagram-style
presets, style single lines, import from Google Sheets, preview frames, export cover images and render MP4s.

    pip install -r requirements.txt
    python mcp_server/anyhouse_mcp.py          # stdio transport (what Claude Desktop / Claude Code launch)

Read docs/MCP.md for the tool reference and skills/anyhouse-video-studio/SKILL.md for the agent playbook.
"""
import asyncio, contextlib, io, json, shutil, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine"))
from mcp.server.fastmcp import FastMCP, Image, Context  # noqa: E402

import render as R  # noqa: E402
import studio as ST  # noqa: E402

ROOT = ST.ROOT
SKILL = ROOT / "skills" / "anyhouse-video-studio"
_lock = threading.RLock()
_jobs, _pool = {}, ThreadPoolExecutor(max_workers=2)

mcp = FastMCP(
    "anyhouse-video-studio",
    instructions=(
        "Builds vertical 1080x1920 text-overlay videos (faceless-channel style) over background clips. "
        "START by reading the resource studio://guide (or call studio_info) - it explains the data model, the workflow "
        "(write content -> pick layout/style -> preview_frame -> fix -> render_videos) and the rules. "
        "Always preview_frame before rendering; rendering is the slow step. Never invent statistics: set status='verify' "
        "on any video containing figures you could not source."))


@contextlib.contextmanager
def quiet():
    """The engine print()s progress; stdout is the MCP transport, so send that to stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def _templates():
    return {t["id"]: t for t in ST.read_templates()}


def _bg_for(item, idx):
    bgs = R.list_bgs()
    if not bgs:
        return None
    with quiet():
        return R.pick_bg(item, bgs, idx, None)


def _png(img, size=None):
    if size:
        img = img.resize(size, R.Image.LANCZOS)
    b = io.BytesIO()
    img.convert("RGB").save(b, "PNG")
    return b.getvalue()


def _video(vid):
    videos = ST.read_content()
    i, v = ST.find_video(videos, vid)
    return videos, i, v


def _timeline(item, tpl):
    layers, total, still = R.build(item, tpl, R.load_brand())
    return layers, total, still


# =================================================================== read
@mcp.tool()
def studio_info() -> dict:
    """Project overview: canvas size, counts, FFmpeg status, folders, and where the guide lives. Call this first."""
    bgs = R.list_bgs()
    return {
        "canvas": {"width": R.W, "height": R.H, "fps": R.FPS, "note": "all positions are fractions of 1080x1920"},
        "videos": len(ST.read_content()), "layouts": len(ST.read_templates()),
        "style_presets": len(ST.read_presets().get("styles", [])), "fonts": len(ST.list_fonts()),
        "background_clips": [b.name for b in bgs],
        "renders": sorted(p.stem for p in (ROOT / "output").glob("*.mp4")),
        "ffmpeg": bool(R.FFMPEG), "project_root": str(ROOT),
        "guide": "read the MCP resource studio://guide (full playbook) and studio://schema (field reference)",
        "web_ui": "python engine/server.py -> http://localhost:8000 (auto-reloads when you change files)",
    }


@mcp.tool()
def list_videos() -> list[dict]:
    """All videos (content items) in a compact form: id, layout, headline, line count, status, whether a render exists."""
    outs = {p.stem for p in (ROOT / "output").glob("*.mp4")}
    return [{"id": v["id"], "layout": v.get("template"), "header": v.get("header", ""), "lines": len(v.get("lines", [])),
             "status": v.get("status", ""), "tags": v.get("tags", []), "rendered": v["id"] in outs}
            for v in ST.read_content()]


@mcp.tool()
def get_video(id: str) -> dict:
    """Full JSON of one video (header, lines incl. per-line style overrides, header_style, timing, caption...)."""
    return _video(id)[2]


@mcp.tool()
def describe_video(id: str) -> dict:
    """What the engine will actually do with a video: layout, total length, and for every on-screen element its
    start/end time, final font size (px) and bounding box. Use it to check timing and text fitting without rendering."""
    _, i, v = _video(id)
    tpl = _templates()[v["template"]]
    layers, total, still = _timeline(v, tpl)
    return {"id": id, "layout": tpl["id"], "mode": tpl.get("mode"), "total_seconds": round(total, 2),
            "best_still_time": round(still, 2), "background": getattr(_bg_for(v, i), "name", "gradient (no clips)"),
            "elements": [{"kind": l["kind"], "index": l["idx"], "start": round(l["start"], 2), "end": round(l["end"], 2),
                          "font_px": l["size"], "x": l["pos"][0], "y": l["pos"][1], "w": l["img"].width, "h": l["img"].height,
                          "entrance": l.get("anim", "fade")} for l in layers]}


@mcp.tool()
def list_layouts() -> list[dict]:
    """Layouts (templates): id, name, category, mode (together = all text at once, stack = lines appear one by one and stay,
    single = one line at a time) and the key timing values."""
    return [{"id": t["id"], "name": t.get("name"), "category": t.get("category"), "mode": t.get("mode"),
             "interval": t.get("interval"), "header_font": (t.get("header") or {}).get("font"),
             "body_font": (t.get("body") or {}).get("font"),
             "used_by": [v["id"] for v in ST.read_content() if v.get("template") == t["id"]]} for t in ST.read_templates()]


@mcp.tool()
def get_layout(id: str) -> dict:
    """Full JSON of one layout (header/body style blocks, timing, sample text)."""
    t = _templates().get(id)
    if not t:
        raise ValueError(f"unknown layout {id!r}. Available: {sorted(_templates())}")
    return t


@mcp.tool()
def list_styles() -> dict:
    """Instagram-style presets (Classic, Modern, Neon pink, Strong yellow box, Typewriter...) with the exact override
    keys each sets, the font files available, and which fonts map to which Instagram text style."""
    p = ST.read_presets()
    return {"note": p.get("_note"), "styles": p["styles"], "instagram_fonts": p["fonts"], "all_font_files": ST.list_fonts()}


@mcp.tool()
def list_backgrounds() -> list[dict]:
    """Background clips available in inbox/ (name + size). A video picks one by 'background' name, by 'tags' matching the
    file name (e.g. file utrecht_canal.mp4 matches tag 'utrecht'), otherwise rotates through them."""
    return [{"name": b.name, "mb": round(b.stat().st_size / 1e6, 1)} for b in R.list_bgs()]


@mcp.tool()
def list_renders() -> list[dict]:
    """Rendered MP4s in output/ with size and modified time, plus covers exported so far."""
    out = [{"file": str(p), "mb": round(p.stat().st_size / 1e6, 1), "modified": time.ctime(p.stat().st_mtime)}
           for p in sorted((ROOT / "output").glob("*.mp4"))]
    out += [{"file": str(p), "kind": "cover"} for p in sorted((ROOT / "output" / "covers").glob("*.png"))]
    return out


# =================================================================== preview / images
@mcp.tool()
def preview_frame(id: str, t: float | None = None, width: int = 540) -> list:
    """Render ONE still frame of a video as an image you can look at (fast, no FFmpeg render). t = seconds into the video
    (default: the moment the last line has appeared). Always do this and LOOK at the result before rendering - check
    text fits, nothing overlaps the Reels UI zones (top 13%, bottom 20%, right edge), colors are readable."""
    _, i, v = _video(id)
    tpl = _templates()[v["template"]]
    with quiet():
        layers, total, still = _timeline(v, tpl)
        img = R.composite_still(R.still_background(_bg_for(v, i)), layers, still if t is None else float(t), {**R.DEFAULT_TPL, **tpl}["darken"])
    width = max(200, min(1080, width))
    data = _png(img, (width, int(width * R.H / R.W)))
    return [f"{id} at t={still if t is None else t:.2f}s of {total:.1f}s (layout {tpl['id']})", Image(data=data, format="png")]


@mcp.tool()
def export_cover(id: str, t: float | None = None, include_text: bool = True, name: str = "") -> dict:
    """Export a full-resolution 1080x1920 PNG still (a thumbnail / cover / story image) of a video to output/covers/.
    include_text=False gives the clean darkened background frame only (for use in other design tools). Returns the file path."""
    _, i, v = _video(id)
    tpl = _templates()[v["template"]]
    with quiet():
        layers, total, still = _timeline(v, tpl)
        img = R.composite_still(R.still_background(_bg_for(v, i)), layers if include_text else [], still if t is None else float(t),
                                {**R.DEFAULT_TPL, **tpl}["darken"])
    d = ROOT / "output" / "covers"
    d.mkdir(parents=True, exist_ok=True)
    path = d / (ST.slug(name or f"{id}_{'cover' if include_text else 'bg'}") + ".png")
    img.convert("RGB").save(path, "PNG")
    return {"path": str(path), "size": [R.W, R.H], "t": still if t is None else t}


# =================================================================== write: videos
@mcp.tool()
def upsert_video(video: dict, replace_existing: bool = True) -> dict:
    """Create a video, or replace the one with the same id. Required: template (layout id) and header and/or lines.
    id is optional (slugified from the header). lines: list of strings, or objects {"text": "...", "color": "#hex", "size": 70,
    "font": "Gabarito-Bold.ttf", "anim": "slide_up", ...} (see studio://schema for every key). Use ' | ' or a real newline
    inside a string for a line break within one on-screen line. Returns the saved video plus any warnings."""
    with _lock:
        videos = ST.read_content()
        video = dict(video)
        video.setdefault("id", ST.unique_id(video.get("header", "video"), [v["id"] for v in videos]))
        video["id"] = ST.slug(video["id"])
        video["lines"] = [x.replace(" | ", "\n") if isinstance(x, str) else x for x in video.get("lines", [])]
        clean, warn = ST.validate_video(video, _templates())
        for k, i in [(v["id"], n) for n, v in enumerate(videos)]:
            if k == clean["id"]:
                if not replace_existing:
                    raise ValueError(f"video {k!r} already exists (pass replace_existing=true or use update_video)")
                videos[i] = clean
                break
        else:
            videos.append(clean)
        ST.write_content(videos)
    return {"saved": clean, "warnings": warn, "next": "preview_frame(id) to look at it, then render_videos([id])"}


@mcp.tool()
def update_video(id: str, patch: dict) -> dict:
    """Shallow-merge `patch` into an existing video. A key set to null is removed. Example: {"header": "New hook",
    "interval": 1.5, "template": "step_single_box", "status": null}. To replace lines pass the whole 'lines' list."""
    with _lock:
        videos, i, v = _video(id)
        for k, val in patch.items():
            if val is None:
                v.pop(k, None)
            else:
                v[k] = val
        if "lines" in patch and patch["lines"] is not None:
            v["lines"] = [x.replace(" | ", "\n") if isinstance(x, str) else x for x in v["lines"]]
        clean, warn = ST.validate_video(v, _templates())
        videos[i] = clean
        ST.write_content(videos)
    return {"saved": clean, "warnings": warn}


@mcp.tool()
def delete_video(id: str, delete_render: bool = False) -> dict:
    """Remove a video from the list (its rendered MP4 is kept unless delete_render=true)."""
    with _lock:
        videos, i, _ = _video(id)
        videos.pop(i)
        ST.write_content(videos)
    removed = False
    if delete_render:
        p = ROOT / "output" / f"{id}.mp4"
        if p.exists():
            p.unlink()
            removed = True
    return {"deleted": id, "render_deleted": removed, "remaining": len(videos)}


@mcp.tool()
def duplicate_video(id: str, new_id: str = "") -> dict:
    """Copy a video (including all style overrides) to a new id, placed right after the original."""
    with _lock:
        videos, i, v = _video(id)
        c = json.loads(json.dumps(v))
        c["id"] = ST.unique_id(new_id or id + "_copy", [x["id"] for x in videos])
        videos.insert(i + 1, c)
        ST.write_content(videos)
    return {"created": c["id"]}


@mcp.tool()
def style_element(id: str, element: str, preset: str = "", style: dict | None = None, clear: bool = False) -> dict:
    """Style ONE on-screen element of ONE video. element = 'header', 'line:0' (first line, 0-based), 'lines' (every line)
    or 'all' (header + lines). Give `preset` (an id from list_styles, e.g. 'neon_pink', 'strong_yellow') and/or `style`
    (override keys such as {"color":"#FFD21F","size":80,"bg_mode":"line","bg_color":"#000000","anim":"slide_up","dx":0,"dy":-40}).
    The preset is applied first (it resets font/color/outline/shadow/glow/box), then `style` on top. clear=true removes
    all overrides from the element instead."""
    with _lock:
        videos, i, v = _video(id)
        if element in ("lines", "all"):
            targets = [f"line:{n}" for n in range(len(v.get("lines", [])))] + (["header"] if element == "all" else [])
        else:
            targets = [element]
        extra = style or {}
        bad = set(extra) - ST.ELEMENT_KEYS
        if bad:
            raise ValueError(f"unknown style keys {sorted(bad)}. Valid: {sorted(ST.ELEMENT_KEYS)}")
        pst = ST.preset_by_id(preset)["style"] if preset else {}
        for el in targets:
            if el != "header" and not (el.startswith("line:") and el[5:].isdigit() and int(el[5:]) < len(v["lines"])):
                raise ValueError(f"bad element {el!r}: use 'header', 'line:N' (0-based, < {len(v['lines'])}), 'lines' or 'all'")
            if clear:
                ov = {"text": ST.element_override(v, el)["text"]} if el != "header" else {}
            else:
                ov = ST.element_override(v, el)
                if pst:
                    ov = ST.apply_preset_flat(ov, pst)
                ov.update(extra)
            ST.set_element_override(v, el, ov)
        videos[i] = v
        ST.write_content(videos)
    return {"id": id, "styled": targets, "video": v}


# =================================================================== write: layouts
@mcp.tool()
def upsert_layout(layout: dict) -> dict:
    """Create or replace a layout (template). Needs id, name, category, mode ('together'|'stack'|'single'), and header/body
    style blocks (font, max_size, min_size, color, stroke, align, upper, y, box_h, x_margin, bg{mode,color,opacity,radius},
    shadow{color,dy,blur}, glow{color,radius}). y/box_h/x_margin are fractions of the frame. Tip: get_layout an existing one,
    modify, and upsert under a new id."""
    for k in ("id", "name", "mode"):
        if not layout.get(k):
            raise ValueError(f"layout needs '{k}'")
    if layout["mode"] not in ("together", "stack", "single"):
        raise ValueError("mode must be together | stack | single")
    with _lock:
        tpls = ST.read_templates()
        layout = dict(layout)
        layout["id"] = ST.slug(layout["id"])
        for n, t in enumerate(tpls):
            if t["id"] == layout["id"]:
                tpls[n] = layout
                break
        else:
            tpls.append(layout)
        ST.write_templates(tpls)
    return {"saved": layout["id"], "layouts": len(tpls)}


@mcp.tool()
def delete_layout(id: str) -> dict:
    """Delete a layout. Refused if any video still uses it."""
    with _lock:
        used = [v["id"] for v in ST.read_content() if v.get("template") == id]
        if used:
            raise ValueError(f"layout {id!r} is used by {used}; move those videos to another layout first")
        tpls = [t for t in ST.read_templates() if t["id"] != id]
        ST.write_templates(tpls)
    return {"deleted": id, "layouts": len(tpls)}


@mcp.tool()
def set_layout_style(layout_id: str, target: str, preset: str) -> dict:
    """Apply an Instagram-style preset to a layout's 'header' or 'body' block, so EVERY video using that layout changes.
    (Per-video tweaks stay in style_element.)"""
    if target not in ("header", "body"):
        raise ValueError("target must be 'header' or 'body'")
    with _lock:
        tpls = ST.read_templates()
        t = next((x for x in tpls if x["id"] == layout_id), None)
        if not t:
            raise ValueError(f"unknown layout {layout_id!r}")
        t[target] = {**(t.get(target) or {}), **ST.flat_to_template_style(ST.preset_by_id(preset)["style"])}
        ST.write_templates(tpls)
    return {"layout": layout_id, "target": target, "preset": preset, "block": t[target]}


# =================================================================== backgrounds / sheets
@mcp.tool()
def add_background(source_path: str, name: str = "") -> dict:
    """Copy a video file from a local path into inbox/ so it can be used as a background clip."""
    src = Path(source_path).expanduser()
    if not src.is_file() or src.suffix.lower() not in R.VIDEO_EXT:
        raise ValueError(f"{source_path!r} is not an existing video file ({sorted(R.VIDEO_EXT)})")
    dest = ROOT / "inbox" / (name or src.name)
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(src, dest)
    return {"added": dest.name, "clips": [b.name for b in R.list_bgs()]}


@mcp.tool()
def import_sheet(url: str = "", tab: str = "", api_key: str = "", csv_text: str = "", mapping: dict | None = None,
                 layout: str = "", duplicates: str = "skip", dry_run: bool = True) -> dict:
    """Import videos from a Google Sheet (shared 'Anyone with the link - Viewer', or a published CSV link) or from CSV/TSV text.
    One row = one video. Columns are auto-detected by header name: Headline/Title/Hook, Body (newline separated lines) or
    Line 1..N, Layout, Tags, Background, CTA, Caption, Hashtags, ID, Status. Override with mapping={"header":"Hook",
    "lines":"Script"}. layout = default layout id when the sheet has none. duplicates='skip'|'update' (match by id or headline).
    ALWAYS run with dry_run=true first and check the preview; then call again with dry_run=false to save."""
    table = ST.parse_rows(csv_text) if csv_text.strip() else ST.fetch_sheet(url, tab, api_key)
    if not table["headers"]:
        raise ValueError("no rows found - is the first row a header row?")
    tpls = ST.read_templates()
    if layout and layout not in {t["id"] for t in tpls}:
        raise ValueError(f"unknown layout {layout!r}")
    new = ST.table_to_videos(table, mapping, layout or None, tpls)
    info = {"columns": table["headers"], "auto_mapping": {k: (table["headers"][i] if i >= 0 else None) for k, i in ST.auto_mapping(table["headers"]).items()},
            "rows_in_sheet": len(table["rows"]), "videos_parsed": len(new),
            "preview": [{"id": v["id"], "header": v["header"], "lines": len(v["lines"]), "layout": v["template"]} for v in new[:8]]}
    if dry_run:
        return {**info, "dry_run": True, "next": "call again with dry_run=false to save"}
    with _lock:
        videos = ST.read_content()
        added, updated, skipped = ST.merge_imported(videos, new, duplicates)
        ST.write_content(videos)
    return {**info, "dry_run": False, "added": added, "updated": updated, "skipped": skipped}


# =================================================================== render
def _render_job(vid, quality, gpu):
    def prog(p):
        _jobs[vid]["progress"] = round(p, 3)
    try:
        videos = ST.read_content()
        idx, item = next((n, v) for n, v in enumerate(videos) if v["id"] == vid)
        t0 = time.time()
        with quiet():
            bg = R.pick_bg(item, R.list_bgs(), idx, None)
            out = R.render_item(item, idx, {}, R.list_bgs(), True, bg, quality, gpu, prog, _templates()[item["template"]])
        _jobs[vid] = {"status": "done", "progress": 1, "file": str(out), "seconds": round(time.time() - t0, 1),
                      "mb": round(Path(out).stat().st_size / 1e6, 1)}
    except BaseException as e:  # SystemExit (no clips) included
        _jobs[vid] = {"status": "error", "progress": 0, "error": str(e) or e.__class__.__name__}


@mcp.tool()
async def render_videos(ids: list[str], quality: str = "standard", gpu: bool = False, wait: bool = True,
                        ctx: Context | None = None) -> dict:
    """Render MP4s (1080x1920, H.264) into output/. quality: 'draft' (720p, fastest - use to check motion/timing),
    'standard' (1080p), 'high'. Needs FFmpeg and at least one background clip in inbox/. wait=true blocks (with progress)
    until all finish; wait=false returns immediately and you poll render_status. Two videos render in parallel.
    Preview with preview_frame first - renders are the slow step."""
    if quality not in R.QUALITY:
        raise ValueError(f"quality must be one of {list(R.QUALITY)}")
    if not R.FFMPEG:
        with quiet():
            R.ensure_ffmpeg(install=True)
    if not R.FFMPEG:
        raise RuntimeError("FFmpeg not found. Install it (winget install Gyan.FFmpeg) or pip install imageio-ffmpeg, then retry.")
    if not R.list_bgs():
        raise RuntimeError("No background clips in inbox/. Add one with add_background or drop .mp4 files into inbox/.")
    known = {v["id"] for v in ST.read_content()}
    missing = [i for i in ids if i not in known]
    if missing:
        raise ValueError(f"unknown video ids {missing}")
    for vid in ids:
        _jobs[vid] = {"status": "running", "progress": 0}
        _pool.submit(_render_job, vid, quality, gpu)
    if not wait:
        return {"started": ids, "next": "poll render_status()"}
    while any(_jobs[i]["status"] == "running" for i in ids):
        if ctx:
            await ctx.report_progress(sum(_jobs[i]["progress"] for i in ids) / len(ids), 1.0)
        await asyncio.sleep(1)
    return {"results": {i: _jobs[i] for i in ids}}


@mcp.tool()
def render_status() -> dict:
    """Status/progress of renders started in this MCP session (status: running | done | error)."""
    return dict(_jobs)


# =================================================================== guide as resources + prompt
@mcp.resource("studio://guide")
def guide() -> str:
    """The full agent playbook (SKILL.md)."""
    p = SKILL / "SKILL.md"
    return p.read_text(encoding="utf-8") if p.exists() else "Guide missing: see skills/anyhouse-video-studio/SKILL.md"


@mcp.resource("studio://schema")
def schema() -> str:
    """Field reference for videos, lines, styles and layouts."""
    p = SKILL / "references" / "schema.md"
    return p.read_text(encoding="utf-8") if p.exists() else "Schema missing: see skills/anyhouse-video-studio/references/schema.md"


@mcp.resource("studio://extending")
def extending() -> str:
    """How to extend the project itself (new effects, exporters, tools)."""
    p = ROOT / "AGENTS.md"
    return p.read_text(encoding="utf-8") if p.exists() else "see AGENTS.md"


@mcp.prompt()
def make_videos(topic: str, count: int = 5, audience: str = "expats renting in the Netherlands") -> str:
    """Kick off a content run: research, write, preview and render videos about a topic."""
    return (f"Read studio://guide first. Then create {count} short vertical videos about: {topic}. Audience: {audience}. "
            "Research and fact-check any figures (cite sources in the video's caption, set status='verify' if unsure), write a strong hook "
            "headline and 3-6 punchy lines per video, pick a fitting layout and Instagram style, preview_frame each video and fix "
            "fitting/contrast problems, then render_videos with quality='draft' for review. Finish with a short report: ids, hooks, sources, open questions.")


if __name__ == "__main__":
    mcp.run()
