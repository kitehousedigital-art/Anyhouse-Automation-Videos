"""Shared data layer for the AnyHouse Video Studio.

Used by BOTH the local web UI (engine/server.py) and the MCP server (mcp_server/anyhouse_mcp.py), so an agent and a
human edit exactly the same files:  content/ideas.json (videos), templates/templates.json (layouts),
presets.json (Instagram-style presets), brand.json (footer / CTA), inbox/ (background clips), output/ (renders).
"""
import csv, io, json, os, re, tempfile, urllib.error, urllib.parse, urllib.request
from pathlib import Path

import render as R

ROOT = R.ROOT
CONTENT = ROOT / "content" / "ideas.json"
TEMPLATES = ROOT / "templates" / "templates.json"
PRESETS = ROOT / "presets.json"
FONT_EXT = {".ttf", ".otf"}

# style keys a preset resets/sets on a single element (flat override form, see docs/CONTENT_SCHEMA.md)
VIS = ["font", "color", "stroke", "stroke_color", "upper", "bg_mode", "bg_color", "bg_opacity", "bg_radius",
       "shadow_on", "shadow_color", "shadow_blur", "shadow_dy", "glow_color", "glow_r"]
# every per-element override key the engine understands
ELEMENT_KEYS = set(VIS) | {"text", "size", "dx", "dy", "align", "line_spacing", "opacity", "rotate",
                           "anim", "anim_d", "delay", "show"}
VIDEO_KEYS = {"id", "template", "header", "lines", "header_style", "interval", "hold", "header_delay", "background",
              "tags", "cta", "status", "caption", "hashtags"}


# ------------------------------------------------------------------ files
def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_content():
    data = R.load_json(CONTENT)
    return data["videos"] if isinstance(data, dict) else data


def write_content(videos):
    _atomic_write(CONTENT, json.dumps({"_note": "Edited in the web UI or via the MCP. status:verify = check figures before posting.",
                                       "videos": videos}, indent=2, ensure_ascii=False))


def read_templates():
    return R.load_json(TEMPLATES)["templates"]


def write_templates(tpls):
    _atomic_write(TEMPLATES, json.dumps({"_help": "mode: together | stack | single. Positions are fractions of the 1080x1920 frame.",
                                         "templates": tpls}, indent=2, ensure_ascii=False))


def read_presets():
    return R.load_json(PRESETS) if PRESETS.exists() else {"fonts": [], "styles": []}


def mtimes():
    return {"content": CONTENT.stat().st_mtime if CONTENT.exists() else 0,
            "templates": TEMPLATES.stat().st_mtime if TEMPLATES.exists() else 0}


def list_fonts():
    return sorted(p.name for p in (ROOT / "fonts").glob("*") if p.suffix.lower() in FONT_EXT)


# ------------------------------------------------------------------ videos
def slug(text):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40] or "video"


def unique_id(base, existing):
    base, n, i = slug(base), None, 2
    n = base
    while n in existing:
        n = f"{base}_{i}"
        i += 1
    return n


def validate_video(v, templates=None):
    """-> (clean_video, warnings). Raises ValueError for things that would break rendering."""
    if not isinstance(v, dict):
        raise ValueError("video must be an object")
    templates = templates or {t["id"]: t for t in read_templates()}
    warn = []
    v = {k: val for k, val in v.items() if val is not None}
    unknown = set(v) - VIDEO_KEYS
    if unknown:
        warn.append(f"unknown video keys kept but ignored by the engine: {sorted(unknown)}")
    if not v.get("header") and not v.get("lines"):
        raise ValueError("a video needs a header and/or lines")
    if v.get("template") not in templates:
        raise ValueError(f"unknown template {v.get('template')!r}. Available: {sorted(templates)}")
    if not isinstance(v.get("lines", []), list):
        raise ValueError("lines must be a list of strings or objects")
    v.setdefault("lines", [])
    for i, ln in enumerate(v["lines"]):
        if isinstance(ln, dict):
            if "text" not in ln:
                raise ValueError(f"lines[{i}] object needs a 'text' key")
            bad = set(ln) - ELEMENT_KEYS
            if bad:
                warn.append(f"lines[{i}] has unknown keys {sorted(bad)}")
        elif not isinstance(ln, str):
            raise ValueError(f"lines[{i}] must be a string or an object with 'text'")
    bad = set(v.get("header_style") or {}) - ELEMENT_KEYS
    if bad:
        warn.append(f"header_style has unknown keys {sorted(bad)}")
    return v, warn


def find_video(videos, vid):
    for i, v in enumerate(videos):
        if v.get("id") == vid:
            return i, v
    raise KeyError(f"no video with id {vid!r}. Existing: {[x.get('id') for x in videos]}")


def apply_preset_flat(override, preset_style):
    """Reset the visual keys of one element override, then apply the preset (same semantics as the UI)."""
    o = {k: v for k, v in override.items() if k not in VIS}
    o.update(preset_style)
    return o


def flat_to_template_style(f):
    o = {"font": f.get("font"), "color": f.get("color"), "upper": bool(f.get("upper")),
         "stroke": f.get("stroke") or 0, "stroke_color": f.get("stroke_color") or "#000000", "glow": None}
    if f.get("bg_mode") == "none":
        o["bg"] = None
    elif f.get("bg_mode"):
        o["bg"] = {"mode": f["bg_mode"], "color": f.get("bg_color", "#000000"), "opacity": f.get("bg_opacity", 1),
                   "radius": f.get("bg_radius", 28), "pad_x": 28, "pad_y": 8, "full": False}
    if f.get("shadow_on") is False:
        o["shadow"] = None
    elif f.get("shadow_on"):
        o["shadow"] = {"color": f.get("shadow_color", "#000000AA"), "dy": f.get("shadow_dy", 6), "blur": f.get("shadow_blur", 8)}
    if f.get("glow_color"):
        o["glow"] = {"color": f["glow_color"], "radius": f.get("glow_r", 18)}
    return o


def preset_by_id(pid):
    for s in read_presets().get("styles", []):
        if s["id"] == pid:
            return s
    raise KeyError(f"unknown style preset {pid!r}. Available: {[s['id'] for s in read_presets().get('styles', [])]}")


def element_override(video, element):
    """element: 'header' | 'line:N' (0-based) -> dict (a copy) of that element's overrides."""
    if element == "header":
        return dict(video.get("header_style") or {})
    i = int(element.split(":")[1])
    ln = video["lines"][i]
    return dict(ln) if isinstance(ln, dict) else {"text": ln}


def set_element_override(video, element, ov):
    ov = {k: v for k, v in ov.items() if v is not None and v != ""}
    if element == "header":
        if ov:
            video["header_style"] = ov
        else:
            video.pop("header_style", None)
    else:
        i = int(element.split(":")[1])
        video["lines"][i] = ov["text"] if list(ov) == ["text"] else ov


# ------------------------------------------------------------------ Google Sheets / CSV
def _http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "AnyHouseVideoStudio/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig", "replace"), r.headers.get("Content-Type", "")


def parse_rows(text):
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0]
    delim = "\t" if "\t" in first and first.count("\t") >= first.count(",") else ","  # pasted from Sheets = tab separated
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return {"headers": [], "rows": []}
    heads = [h.strip() for h in rows[0]]
    return {"headers": heads, "rows": [r + [""] * (len(heads) - len(r)) for r in rows[1:]]}


def fetch_sheet(url, tab="", api_key=""):
    """Public Google Sheet (shared 'anyone with the link') or published/direct CSV -> {headers, rows}."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Paste the Google Sheet link first.")
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
    if not m:
        text, _ = _http_get(url)
        return parse_rows(text)
    sid = m.group(1)
    gid = (re.search(r"[#&?]gid=(\d+)", url) or [None, None])[1]
    try:
        if api_key:
            meta_url = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}?fields=sheets.properties&key={api_key}"
            rng = urllib.parse.quote(tab) if tab else None
            if not rng:
                sheets = json.loads(_http_get(meta_url)[0])["sheets"]
                pick = next((s for s in sheets if gid and str(s["properties"]["sheetId"]) == gid), sheets[0])
                rng = urllib.parse.quote(pick["properties"]["title"])
            vals = json.loads(_http_get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{rng}?key={api_key}")[0]).get("values", [])
            if not vals:
                return {"headers": [], "rows": []}
            heads = [str(h).strip() for h in vals[0]]
            return {"headers": heads, "rows": [[str(c) for c in r] + [""] * (len(heads) - len(r)) for r in vals[1:]]}
        if tab:
            export = f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(tab)}"
        else:
            export = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv" + (f"&gid={gid}" if gid else "")
        text, ctype = _http_get(export)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise ValueError("Google refused access. Share the sheet as 'Anyone with the link' (Viewer), or File > Share > "
                             "Publish to web, or provide a Google API key.")
        raise
    if "text/html" in ctype or text.lstrip().lower().startswith("<!doctype"):
        raise ValueError("The sheet is private. Set sharing to 'Anyone with the link' (Viewer) and try again.")
    return parse_rows(text)


SHEET_FIELDS = ["header", "lines", "template", "tags", "background", "cta", "caption", "hashtags", "id", "status"]
_AUTO = {"header": r"^(head(er|line)?|title|hook)$", "lines": r"^(body|content|lines?|points?|text|script|bullets?)$",
         "template": r"^(template|layout|style)$", "tags": r"^(tags?|city|cities|location)$",
         "background": r"^(background|clip|bg|video)$", "cta": r"^(cta|call.?to.?action)$",
         "caption": r"^(caption|description|post.?text)$", "hashtags": r"^(hash.?tags?)$",
         "id": r"^(id|slug|file.?(name|id))$", "status": r"^(status|verify|verified)$"}
_LINECOL = re.compile(r"^(line|point|bullet|l)[\s_-]*\d+$", re.I)


def auto_mapping(headers):
    m = {f: next((i for i, h in enumerate(headers) if re.match(_AUTO[f], h.strip(), re.I)), -1) for f in SHEET_FIELDS}
    if m["header"] < 0 and headers:
        m["header"] = 0
    return m


def table_to_videos(table, mapping=None, default_layout=None, templates=None):
    """Sheet/CSV table -> list of video dicts. mapping: {field: column name or index} (default: auto-detect by header)."""
    heads, rows = table["headers"], table["rows"]
    templates = templates or read_templates()
    tids = {t["id"].lower(): t["id"] for t in templates}
    tnames = {(t.get("name") or "").lower(): t["id"] for t in templates}
    default_layout = default_layout or templates[0]["id"]
    m = auto_mapping(heads)
    for f, c in (mapping or {}).items():
        if isinstance(c, str):
            c = next((i for i, h in enumerate(heads) if h.strip().lower() == c.strip().lower()), -1)
        m[f] = -1 if c is None else int(c)
    line_cols = [i for i, h in enumerate(heads) if _LINECOL.match(h.strip())]
    out = []
    for r in rows:
        def g(f):
            return str(r[m[f]]).strip() if m.get(f, -1) >= 0 and m[f] < len(r) else ""
        header = g("header")
        if not header:
            continue
        lines = [re.sub(r"\s*\|\s*", "\n", str(r[i]).strip()) for i in line_cols if i < len(r) and str(r[i]).strip()]
        if not lines and g("lines"):
            lines = [re.sub(r"\s*\|\s*", "\n", ln.strip()) for ln in g("lines").split("\n") if ln.strip()]
        key = g("template").lower()
        v = {"id": slug(g("id") or header), "template": tids.get(key) or tnames.get(key) or default_layout,
             "header": header, "lines": lines}
        if g("tags"):
            v["tags"] = [t.strip() for t in re.split(r"[,;]", g("tags")) if t.strip()]
        for f in ("background", "cta"):
            if g(f):
                v[f] = g(f)
        cap = "\n".join(x for x in (g("caption"), g("hashtags")) if x)
        if cap:
            v["caption"] = cap
        if re.search(r"verify|check|todo|needs|draft", g("status"), re.I):
            v["status"] = "verify"
        out.append(v)
    return out


def merge_imported(videos, new, duplicates="skip"):
    """Append new videos (unique ids). duplicates: 'skip' | 'update' (match by id or headline). -> (added, updated, skipped)"""
    ids = [v["id"] for v in videos]
    added = updated = skipped = 0
    for it in new:
        ex = next((v for v in videos if v["id"] == it["id"] or str(v.get("header", "")).strip().lower() == it["header"].lower()), None)
        if ex:
            if duplicates == "update":
                ex["header"] = it["header"]
                ex["lines"] = [({**ex["lines"][i], "text": t} if i < len(ex["lines"]) and isinstance(ex["lines"][i], dict) else t)
                               for i, t in enumerate(it["lines"])]
                for k in ("tags", "background", "cta", "caption", "status"):
                    if k in it:
                        ex[k] = it[k]
                updated += 1
            else:
                skipped += 1
            continue
        it["id"] = unique_id(it["id"], ids)
        ids.append(it["id"])
        videos.append(it)
        added += 1
    return added, updated, skipped
