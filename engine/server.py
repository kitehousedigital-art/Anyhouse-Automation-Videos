#!/usr/bin/env python3
"""Local web UI for the AnyHouse video engine.   python engine/server.py   ->  http://localhost:8000"""
import csv, io, json, os, re, subprocess, sys, threading, time, webbrowser
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render as R
import studio as ST
from studio import (read_content, write_content, read_templates, write_templates, read_presets, parse_rows,
                    fetch_sheet, list_fonts)

ROOT = R.ROOT
UI = ROOT / "ui" / "index.html"
CONTENT = ROOT / "content" / "ideas.json"
TEMPLATES = ROOT / "templates" / "templates.json"
SETTINGS = ROOT / "settings.json"
FONT_EXT = {".ttf", ".otf"}
JOBS, JOB_LOCK = {}, threading.Lock()
POOL = ThreadPoolExecutor(max_workers=2)  # two videos at a time
_bg_cache = {}


def safe(name):
    return re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name).name)


def bg_image(name=None):
    key = name or ""
    if key not in _bg_cache:
        path = (ROOT / "inbox" / safe(name)) if name else None
        _bg_cache[key] = R.still_background(path if path and path.exists() else None)
    return _bg_cache[key]


def read_settings():
    d = {"quality": "standard", "gpu": False, "autosave": True}
    if SETTINGS.exists():
        d.update(R.load_json(SETTINGS))
    return d


def png_bytes(img, size=None):
    if size:
        img = img.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_preview(item, tpl, t, bg_name):
    layers, total, still = R.build(item, tpl, R.load_brand())
    img = R.composite_still(bg_image(bg_name), layers, still if t is None else float(t), {**R.DEFAULT_TPL, **tpl}["darken"])
    els = [[l["kind"], l["idx"], l["pos"][0], l["pos"][1], l["img"].width, l["img"].height,
            round(l["start"], 2), round(l["end"], 2), l["size"]] for l in layers if l["kind"] in ("header", "line")]
    return png_bytes(img, (540, 960)), total, still, els


def run_job(vid, idx, item, tpl, quality, gpu):
    def prog(p):
        with JOB_LOCK:
            JOBS[vid]["progress"] = round(p, 3)
    try:
        bg = R.pick_bg(item, R.list_bgs(), idx, None)
        t0 = time.time()
        R.render_item(item, idx, {}, R.list_bgs(), True, bg, quality, gpu, prog, tpl)
        with JOB_LOCK:
            JOBS[vid] = {"status": "done", "msg": f"done in {time.time() - t0:.0f}s", "progress": 1}
    except BaseException as e:  # SystemExit from pick_bg included
        with JOB_LOCK:
            JOBS[vid] = {"status": "error", "msg": str(e) or e.__class__.__name__, "progress": 0}


def start_jobs(ids, quality, gpu):
    templates = R.load_templates()
    items = {it["id"]: (i, it) for i, it in enumerate(read_content())}
    for vid in ids:
        if vid not in items:
            continue
        idx, item = items[vid]
        with JOB_LOCK:
            JOBS[vid] = {"status": "running", "msg": "rendering...", "progress": 0}
        POOL.submit(run_job, vid, idx, item, templates.get(item["template"]), quality, gpu)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(body)

    def js(self, obj, code=200):
        self.send(code, json.dumps(obj).encode())

    def body_json(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(200, UI.read_bytes(), "text/html; charset=utf-8")
            if u.path.startswith("/fonts/"):
                fp = ROOT / "fonts" / safe(u.path[7:])
                if fp.suffix.lower() in FONT_EXT and fp.exists():
                    return self.send(200, fp.read_bytes(), "font/ttf", {"Cache-Control": "max-age=3600"})
                return self.send(404, b"not found", "text/plain")
            if u.path == "/favicon.ico":
                return self.send(204)
            if u.path == "/api/state":
                outs = {p.stem: {"mtime": p.stat().st_mtime, "size": p.stat().st_size} for p in (ROOT / "output").glob("*.mp4")}
                bgs = [{"name": b.name, "size": b.stat().st_size} for b in R.list_bgs()]
                fonts = list_fonts()
                with JOB_LOCK:
                    jobs = dict(JOBS)
                return self.js({"templates": read_templates(), "videos": read_content(), "bgs": bgs, "fonts": fonts,
                                "outputs": outs, "jobs": jobs, "presets": read_presets(), "mtimes": ST.mtimes(), "ffmpeg": bool(R.FFMPEG), "settings": read_settings(),
                                "gpu": R.gpu_encoder() if R.FFMPEG else None})
            if u.path == "/api/mtimes":
                return self.js(ST.mtimes())
            if u.path == "/api/jobs":
                with JOB_LOCK:
                    return self.js(dict(JOBS))
            if u.path == "/api/tpl_thumb":
                t = next(x for x in read_templates() if x["id"] == q["id"])
                layers, _, still = R.build(t.get("sample", {}), t, R.load_brand())
                img = R.composite_still(bg_image(None), layers, still, {**R.DEFAULT_TPL, **t}["darken"])
                return self.send(200, png_bytes(img, (270, 480)), "image/png", {"Cache-Control": "max-age=30"})
            if u.path == "/api/bgthumb":
                return self.send(200, png_bytes(bg_image(q["name"]), (180, 320)), "image/png", {"Cache-Control": "max-age=300"})
            if u.path.startswith("/files/output/"):
                return self.serve_file(ROOT / "output" / safe(u.path), "dl" in q)
            if u.path.startswith("/files/inbox/"):
                return self.serve_file(ROOT / "inbox" / safe(u.path), "dl" in q)
        except Exception as e:
            return self.js({"error": str(e)}, 500)
        self.send(404, b"not found", "text/plain")

    def serve_file(self, p, download=False):
        if not p.exists():
            return self.send(404, b"missing", "text/plain")
        size = p.stat().st_size
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m:
            start = int(m.group(1) or 0)
            end = int(m.group(2)) if m.group(2) else end
            code = 206
        with p.open("rb") as f:
            f.seek(start)
            data = f.read(end - start + 1)
        extra = {"Accept-Ranges": "bytes"}
        if code == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        if download:
            extra["Content-Disposition"] = f'attachment; filename="{p.name}"'
        self.send(code, data, "video/mp4", extra)

    def receive_file(self, dest):
        n = int(self.headers.get("Content-Length", 0))
        with dest.open("wb") as f:
            while n > 0:
                chunk = self.rfile.read(min(1 << 20, n))
                if not chunk:
                    break
                f.write(chunk)
                n -= len(chunk)

    def do_POST(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/preview":
                b = self.body_json()
                png, total, still, els = make_preview(b["item"], b["tpl"], b.get("t"), b.get("bg") or None)
                return self.send(200, png, "image/png", {"X-Total": f"{total:.2f}", "X-Still": f"{still:.2f}",
                                                         "X-Elements": json.dumps(els, separators=(",", ":"))})
            if u.path == "/api/content":
                write_content(self.body_json()["videos"])
                return self.js({"ok": True})
            if u.path == "/api/templates":
                write_templates(self.body_json()["templates"])
                return self.js({"ok": True})
            if u.path == "/api/sheet":
                b = self.body_json()
                try:
                    if b.get("csv"):
                        return self.js(parse_rows(b["csv"]))
                    return self.js(fetch_sheet(b.get("url"), b.get("tab", ""), b.get("api_key", "")))
                except ValueError as e:
                    return self.js({"error": str(e)}, 400)
                except urllib.error.URLError as e:
                    return self.js({"error": "Could not reach Google: " + str(e.reason)}, 502)
            if u.path == "/api/settings":
                SETTINGS.write_text(json.dumps(self.body_json()), encoding="utf-8")
                return self.js({"ok": True})
            if u.path == "/api/render":
                b = self.body_json()
                st = read_settings()
                start_jobs(b["ids"], b.get("quality") or st["quality"], b.get("gpu", st["gpu"]))
                return self.js({"ok": True})
            if u.path == "/api/delete":
                b = self.body_json()
                kind, name = b["kind"], safe(b["name"])
                folder = {"bg": ROOT / "inbox", "output": ROOT / "output", "font": ROOT / "fonts"}[kind]
                f = folder / (name + ".mp4" if kind == "output" and not name.endswith(".mp4") else name)
                if f.exists():
                    f.unlink()
                _bg_cache.pop(name, None)
                return self.js({"ok": True})
            if u.path == "/api/upload":
                name = safe(q["name"])
                if Path(name).suffix.lower() not in R.VIDEO_EXT:
                    return self.js({"error": "not a video file"}, 400)
                (ROOT / "inbox").mkdir(exist_ok=True)
                self.receive_file(ROOT / "inbox" / name)
                _bg_cache.pop(name, None)
                return self.js({"ok": True, "name": name})
            if u.path == "/api/font_upload":
                name = safe(q["name"])
                if Path(name).suffix.lower() not in FONT_EXT:
                    return self.js({"error": "use .ttf or .otf"}, 400)
                self.receive_file(ROOT / "fonts" / name)
                R.load_font.cache_clear()
                return self.js({"ok": True, "name": name})
            if u.path == "/api/setup_ffmpeg":
                ok = bool(R.ensure_ffmpeg(install=True))
                _bg_cache.clear()
                return self.js({"ok": ok})
            if u.path == "/api/open_folder":
                folder = ROOT / ("output" if self.body_json().get("which") != "inbox" else "inbox")
                if hasattr(os, "startfile"):
                    os.startfile(folder)  # Windows
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(folder)])
                else:
                    subprocess.Popen(["xdg-open", str(folder)])
                return self.js({"ok": True})
        except Exception as e:
            return self.js({"error": str(e)}, 500)
        self.send(404, b"not found", "text/plain")


def main():
    port = int(os.environ.get("PORT", 8000))
    for d in ("output", "inbox", "fonts"):
        (ROOT / d).mkdir(exist_ok=True)
    if not R.ensure_ffmpeg(install=True):
        print("WARNING: FFmpeg not found and automatic install failed. Run: pip install imageio-ffmpeg")
    else:
        print("FFmpeg:", R.FFMPEG)
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://localhost:{port}"
    print(f"AnyHouse Video Studio running at {url}   (Ctrl+C to stop)")
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
