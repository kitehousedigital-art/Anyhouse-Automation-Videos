#!/usr/bin/env python3
"""
AnyHouse text-overlay video engine (Plan A: pure code, zero AI tokens).

  python engine/render.py list                      # show templates by category
  python engine/render.py gallery                   # one preview PNG per template + contact sheet
  python engine/render.py preview [--id X]          # still frame for each content item
  python engine/render.py render  [--id X] [--force]# render MP4s into output/
  python engine/render.py watch                     # drop a video in inbox/ -> next pending content renders

Needs: Python 3.9+, Pillow, FFmpeg on PATH.
"""
import argparse, csv, json, re, shutil, subprocess, sys, tempfile, time
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent


def find_ffmpeg():
    """System FFmpeg, FFMPEG_PATH, a winget install, or the copy bundled by `pip install imageio-ffmpeg`."""
    import glob, importlib, os
    for c in (os.environ.get("FFMPEG_PATH"), shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return c
    pats = [r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]
    if os.environ.get("LOCALAPPDATA"):
        pats.insert(0, os.environ["LOCALAPPDATA"] + r"\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe")
    for pat in pats:
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    try:
        importlib.invalidate_caches()
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = find_ffmpeg()


def ensure_ffmpeg(install=True):
    """Find FFmpeg; if missing, pip-install the bundled one (PyPI, so no GitHub needed)."""
    global FFMPEG
    FFMPEG = find_ffmpeg()
    if not FFMPEG and install:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "imageio-ffmpeg"], check=True)
        except Exception as e:
            print("pip install imageio-ffmpeg failed:", e)
        FFMPEG = find_ffmpeg()
    return FFMPEG
W, H, FPS = 1080, 1920, 30
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
# emoji / flags can't be drawn by Pillow reliably on every OS -> stripped (v1.1: Twemoji PNGs)
EMOJI_RE = re.compile("[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF☀-➿️‍⭐⬆⬇]+")

DEFAULT_STYLE = dict(font="Poppins-Bold.ttf", max_size=90, min_size=28, color="#FFFFFF",
                     stroke=0, stroke_color="#000000", align="center", upper=False,
                     line_spacing=1.15, gap=16, x_margin=0.08, y=0.3, box_h=0.4,
                     valign="top", bg=None, shadow=None, glow=None)
DEFAULT_BG = dict(mode="line", color="#000000", opacity=1.0, radius=28, pad_x=28, pad_y=8, full=False)
DEFAULT_TPL = dict(mode="stack", intro=0.4, fade=0.3, interval=2.0, header_delay=0.9,
                   end_hold=2.2, min_hold=3.0, min_duration=6.0, darken=0.2)


# ----------------------------------------------------------------- text helpers
def hexcol(s, opacity=1.0):
    s = s.lstrip("#")
    a = int(s[6:8], 16) if len(s) == 8 else 255
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(a * opacity))


@lru_cache(maxsize=256)
def load_font(name, size):
    for p in (ROOT / "fonts" / name, Path(name), ROOT / "fonts" / "Poppins-Bold.ttf"):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


def mkstyle(d):
    s = {**DEFAULT_STYLE, **(d or {})}
    if s.get("bg"):
        s["bg"] = {**DEFAULT_BG, **s["bg"]}
    return s


def clean(text, st):
    text = EMOJI_RE.sub("", str(text))
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text.upper() if st["upper"] else text


def wrap(para, font, maxw):
    lines, cur = [], ""
    toks, glue = [], ""
    for w in para.split():  # keep "1." / "2)" attached to the following word
        if re.fullmatch(r"\d+[.)]", w):
            glue = w + " "
        else:
            toks.append(glue + w)
            glue = ""
    if glue:
        toks.append(glue.strip())
    for w in toks:
        t = (cur + " " + w).strip()
        if font.getlength(t) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""], all(font.getlength(l) <= maxw for l in lines)


def fit(texts, st, boxw, boxh):
    """Largest font size where every text wraps inside boxw and the stack fits boxh."""
    bg = st["bg"]
    mode = bg["mode"] if bg else None
    padx = bg["pad_x"] if bg else 0
    pady = bg["pad_y"] if bg else 0
    inner = boxw - 2 * padx - 2 * st["stroke"]
    best = None
    for size in range(st["max_size"], st["min_size"] - 1, -2):
        font = load_font(st["font"], size)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * st["line_spacing"])
        wrapped, ok = [], True
        for t in texts:
            ls = []
            for para in t.split("\n"):
                l, o = wrap(para, font, inner)
                ls += l
                ok &= o
            wrapped.append(ls)
        hs = [len(ls) * lh + (2 * pady if mode == "row" else 0) for ls in wrapped]
        total = sum(hs) + st["gap"] * (len(hs) - 1)
        best = (font, wrapped, hs, lh, total)
        if ok and total <= boxh:
            return best
    return best


def tops_for(hs, st, boxh_px):
    total = sum(hs) + st["gap"] * (len(hs) - 1)
    y0 = int(st["y"] * H)
    top = y0 if st["valign"] == "top" else y0 + (boxh_px - total) / 2
    top = max(top, 0.04 * H)
    out, y = [], top
    for h in hs:
        out.append(y)
        y += h + st["gap"]
    return out


def ax(x0, boxw, w, align):
    return x0 if align == "left" else x0 + boxw - w if align == "right" else x0 + (boxw - w) / 2


def draw_items(layer, wrapped, hs, tops, font, lh, st, dx=0):
    d = ImageDraw.Draw(layer)
    bg = st["bg"]
    mode = bg["mode"] if bg else None
    padx = bg["pad_x"] if bg else 0
    pady = bg["pad_y"] if bg else 0
    x0 = int(st["x_margin"] * W)
    boxw = W - 2 * x0
    x0 += dx
    asc, desc = font.getmetrics()
    lead = (lh - (asc + desc)) / 2
    col, scol = hexcol(st["color"]), hexcol(st["stroke_color"])
    shadow = st["shadow"]
    texts = []  # (x, y, line)
    for ls, h, top in zip(wrapped, hs, tops):
        if mode == "row":
            tw = max(font.getlength(l) for l in ls)
            bw = boxw if bg["full"] else tw + 2 * padx
            bx = x0 if bg["full"] else ax(x0, boxw, bw, st["align"])
            d.rounded_rectangle([bx, top, bx + bw, top + h], bg["radius"], fill=hexcol(bg["color"], bg["opacity"]))
            ty = top + pady
            for i, l in enumerate(ls):
                tw = font.getlength(l)
                texts.append((ax(bx + padx, bw - 2 * padx, tw, st["align"]), ty + i * lh + lead, l))
        elif mode == "line":
            for i, l in enumerate(ls):
                tw = font.getlength(l)
                bw = tw + 2 * padx
                bx = ax(x0, boxw, bw, st["align"])
                y = top + i * lh
                d.rounded_rectangle([bx, y - pady, bx + bw, y + lh + pady], bg["radius"],
                                    fill=hexcol(bg["color"], bg["opacity"]))
                texts.append((bx + padx, y + lead, l))
        else:
            for i, l in enumerate(ls):
                tw = font.getlength(l)
                texts.append((ax(x0, boxw, tw, st["align"]), top + i * lh + lead, l))
    if shadow:
        sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ds = ImageDraw.Draw(sh)
        for x, y, l in texts:
            ds.text((x + shadow.get("dx", 0), y + shadow.get("dy", 6)), l, font=font,
                    fill=hexcol(shadow.get("color", "#000000AA")))
        layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(shadow.get("blur", 8))))
    glow = st.get("glow")
    if glow and glow.get("color"):
        r = int(glow.get("radius", 18))
        gl = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        dg = ImageDraw.Draw(gl)
        gc = hexcol(glow["color"])
        for x, y, l in texts:
            dg.text((x, y), l, font=font, fill=gc, stroke_width=max(2, r // 4), stroke_fill=gc)
        blurred = gl.filter(ImageFilter.GaussianBlur(r))
        layer.alpha_composite(blurred)
        layer.alpha_composite(blurred)  # twice = stronger light
    for x, y, l in texts:
        d.text((x, y), l, font=font, fill=col, stroke_width=st["stroke"], stroke_fill=scol)


def new_layer():
    return Image.new("RGBA", (W, H), (255, 255, 255, 0))


def draw_text_layer(texts, st, boxh_frac=None, size=None, dx=0, dy=0):
    """Fit + draw a list of texts as ONE layer. -> (layer, font size)."""
    boxw = W - 2 * int(st["x_margin"] * W)
    boxh = int((boxh_frac or st["box_h"]) * H)
    if size:
        font, ls, h, lh = fit_width(texts[0], st, boxw, int(size))
        wrapped, hs = [ls], [h]
    else:
        font, wrapped, hs, lh, _ = fit(texts, st, boxw, boxh)
    layer = new_layer()
    draw_items(layer, wrapped, hs, [y + dy for y in tops_for(hs, st, boxh)], font, lh, st, dx)
    return layer, font.size


# ----------------------------------------------------------------- timeline
def words(*texts):
    return sum(len(t.split()) for t in texts)


def norm_line(x):
    return dict(x) if isinstance(x, dict) else {"text": str(x)}


def item_style(base, ov):
    """Base style + per-element overrides: color, font, align, stroke, upper, line_spacing,
    box (bg_mode none|line|row, bg_color, bg_opacity, bg_radius), shadow_on/color/blur/dy, glow_color/glow_r."""
    st = dict(base)
    for k in ("color", "font", "align", "stroke", "stroke_color", "upper", "line_spacing"):
        if ov.get(k) not in (None, ""):
            st[k] = ov[k]
    mode = ov.get("bg_mode")
    if mode == "none":
        st["bg"] = None
    elif mode in ("line", "row") or any(ov.get(k) not in (None, "") for k in ("bg_color", "bg_opacity", "bg_radius")):
        bg = {**DEFAULT_BG, **(st.get("bg") or {})}
        if mode in ("line", "row"):
            bg["mode"] = mode
        if ov.get("bg_color"):
            bg["color"] = ov["bg_color"]
        if ov.get("bg_opacity") not in (None, ""):
            bg["opacity"] = float(ov["bg_opacity"])
        if ov.get("bg_radius") not in (None, ""):
            bg["radius"] = int(ov["bg_radius"])
        st["bg"] = bg
    if ov.get("shadow_on") is False:
        st["shadow"] = None
    elif ov.get("shadow_on") or any(ov.get(k) not in (None, "") for k in ("shadow_color", "shadow_blur", "shadow_dy")):
        sh = {"color": "#000000AA", "dy": 6, "blur": 8, **(st.get("shadow") or {})}
        if ov.get("shadow_color"):
            sh["color"] = ov["shadow_color"]
        if ov.get("shadow_blur") not in (None, ""):
            sh["blur"] = float(ov["shadow_blur"])
        if ov.get("shadow_dy") not in (None, ""):
            sh["dy"] = float(ov["shadow_dy"])
        st["shadow"] = sh
    if ov.get("glow_color"):
        st["glow"] = {"color": ov["glow_color"], "radius": int(ov.get("glow_r") or 18)}
    return st


def post_fx(img, ov):
    """Per-element opacity + rotation, applied to the full-canvas layer."""
    rot = float(ov.get("rotate") or 0)
    if rot:
        bb = img.getchannel("A").getbbox()
        if bb:
            img = img.rotate(-rot, resample=Image.BICUBIC, center=((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2))
    op = ov.get("opacity")
    if op not in (None, "") and float(op) < 1:
        a = img.getchannel("A").point(lambda v: int(v * max(0.0, float(op))))
        img.putalpha(a)
    return img


ANIM_OFFSET = {"slide_up": (0, 110), "slide_down": (0, -110), "slide_left": (140, 0), "slide_right": (-140, 0)}


def fit_width(text, st, boxw, size):
    """Fixed font size; shrinks only if a word is wider than the box. -> font, wrapped lines, height, line height."""
    bg = st["bg"]
    mode = bg["mode"] if bg else None
    padx = bg["pad_x"] if bg else 0
    pady = bg["pad_y"] if bg else 0
    inner = boxw - 2 * padx - 2 * st["stroke"]
    for s in range(max(int(size), 10), 9, -2):
        font = load_font(st["font"], s)
        asc, desc = font.getmetrics()
        lh = int((asc + desc) * st["line_spacing"])
        ls, ok = [], True
        for para in text.split("\n"):
            l, o = wrap(para, font, inner)
            ls += l
            ok &= o
        if ok:
            break
    return font, ls, len(ls) * lh + (2 * pady if mode == "row" else 0), lh


def fit_one(text, st, ov, boxw, boxh):
    if ov.get("size"):
        font, ls, h, lh = fit_width(text, st, boxw, int(ov["size"]))
        return font, [ls], [h], lh
    font, wr, hh, lh, _ = fit([text], st, boxw, boxh)
    return font, wr, hh, lh


def timed(layer, ov):
    """Entry animation: none | fade | slide_up/down/left/right. Stored on the layer for the ffmpeg + still compositors."""
    an = ov.get("anim") or "fade"
    if an == "none":
        layer["fin"] = 0
    layer["anim"] = an if an in ANIM_OFFSET else "fade"
    if ov.get("anim_d"):
        layer["fin"] = float(ov["anim_d"])
    elif an in ANIM_OFFSET:
        layer["fin"] = max(layer["fin"], 0.45)
    return layer


def build(item, tpl, brand):
    """-> (layers, total_seconds, still_time). layer = dict(img,start,end,fin,fout,kind,idx,size)."""
    tpl = {**DEFAULT_TPL, **tpl}
    hs, bs = mkstyle(tpl.get("header")), mkstyle(tpl.get("body"))
    hov = item.get("header_style") or {}
    hst = item_style(hs, hov)
    header = clean(item.get("header", ""), hst)
    raws = [norm_line(x) for x in item.get("lines", [])]
    sts = [item_style(bs, r) for r in raws]
    lines = [clean(r.get("text", ""), s) for r, s in zip(raws, sts)]
    mode, t0, fade = tpl["mode"], tpl["intro"], tpl["fade"]
    interval = float(item.get("interval", tpl["interval"]))
    hold = float(item.get("hold", tpl["end_hold"]))
    hdr_delay = float(item.get("header_delay", tpl["header_delay"])) if (header and lines) else 0.0
    n = len(lines)
    layers = []

    if mode == "together":
        starts = [t0 + hdr_delay] * n
        T = t0 + hdr_delay + max(tpl["min_hold"], 0.4 * words(header, *lines))
    else:
        starts = [t0 + hdr_delay + i * interval for i in range(n)]
        T = (starts[-1] if starts else t0) + hold
    T = max(T, tpl["min_duration"])
    still = (starts[-1] if starts else t0) + 0.05

    if header:
        img, fsz = draw_text_layer([header], hst, size=hov.get("size"), dx=int(hov.get("dx", 0)), dy=int(hov.get("dy", 0)))
        hs0 = max(0.0, t0 + float(hov.get("delay") or 0))
        he = min(T, hs0 + float(hov["show"])) if hov.get("show") else T
        layers.append(timed(dict(img=post_fx(img, hov), start=hs0, end=he, fin=fade, fout=0, kind="header", idx=0, size=fsz), hov))

    if lines:
        boxw = W - 2 * int(bs["x_margin"] * W)
        boxh = int(bs["box_h"] * H)
        if mode == "single":
            for i, t in enumerate(lines):
                font, wr, hh, lh = fit_one(t, sts[i], raws[i], boxw, boxh)
                tops = [y + int(raws[i].get("dy", 0)) for y in tops_for(hh, sts[i], boxh)]
                img = new_layer()
                draw_items(img, wr, hh, tops, font, lh, sts[i], int(raws[i].get("dx", 0)))
                st_i = max(0.0, starts[i] + float(raws[i].get("delay") or 0))
                end = (starts[i + 1] if i + 1 < n else T)
                if raws[i].get("show"):
                    end = min(end, st_i + float(raws[i]["show"]))
                layers.append(timed(dict(img=post_fx(img, raws[i]), start=st_i, end=max(end, st_i + 0.3), fin=fade,
                                         fout=0.15 if i + 1 < n else 0, kind="line", idx=i, size=font.size), raws[i]))
        else:  # stack / together: shared base size from all auto-sized lines, so nothing jumps
            auto = [t for t, r in zip(lines, raws) if not r.get("size")] or lines
            base = fit(auto, bs, boxw, boxh)[0].size
            res = [fit_width(t, st, boxw, int(r.get("size") or base)) for t, st, r in zip(lines, sts, raws)]
            hh = [r[2] for r in res]
            tops = tops_for(hh, bs, boxh)
            for i in range(n):
                font, ls, h, lh = res[i]
                img = new_layer()
                draw_items(img, [ls], [h], [tops[i] + int(raws[i].get("dy", 0))], font, lh, sts[i], int(raws[i].get("dx", 0)))
                st_i = max(0.0, starts[i] + float(raws[i].get("delay") or 0))
                end = min(T, st_i + float(raws[i]["show"])) if raws[i].get("show") else T
                layers.append(timed(dict(img=post_fx(img, raws[i]), start=st_i, end=max(end, st_i + 0.3), fin=fade, fout=0,
                                         kind="line", idx=i, size=font.size), raws[i]))

    total = T
    foot = (brand or {}).get("footer")
    if foot and foot.get("enabled", True) and foot.get("text"):
        fs = mkstyle(foot.get("style"))
        layers.append(dict(img=draw_text_layer([foot["text"]], fs, 0.06)[0], start=0.0, end=None, fin=0.4, fout=0,
                           kind="footer", idx=0, size=0))
    cta = (brand or {}).get("cta")
    cta_text = item.get("cta") or (cta.get("text") if cta and cta.get("enabled") else None)
    if cta_text:
        secs = float((cta or {}).get("seconds", 2.5))
        cs = mkstyle((cta or {}).get("style"))
        layers.append(dict(img=draw_text_layer([clean(cta_text, cs)], cs)[0], start=T, end=T + secs, fin=0.3, fout=0,
                           kind="cta", idx=0, size=0))
        total = T + secs
    out = []
    for l in layers:
        if l["end"] is None:
            l["end"] = total
        bb = l["img"].getchannel("A").getbbox()
        if not bb:
            continue
        l["pos"] = (bb[0], bb[1])
        l["img"] = l["img"].crop(bb)
        out.append(l)
    return out, total, still


# ----------------------------------------------------------------- backgrounds
def list_bgs():
    d = ROOT / "inbox"
    return sorted(p for p in d.glob("*") if p.suffix.lower() in VIDEO_EXT) if d.exists() else []


def pick_bg(item, bgs, idx, override=None):
    if override:
        return Path(override)
    want = str(item.get("background", "")).lower()
    if want:
        for b in bgs:
            if want in b.name.lower():
                return b
    for tag in item.get("tags", []):
        for b in bgs:
            if str(tag).lower() in b.name.lower():
                return b
    if not bgs:
        sys.exit("No background videos found in inbox/. Drop .mp4/.mov files there.")
    return bgs[idx % len(bgs)]


def still_background(bg=None):
    """First frame of a real background (or a gradient stand-in) as a 1080x1920 RGB image."""
    if bg and FFMPEG:
        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "f.png"
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "0.5", "-i", str(bg), "-frames:v", "1",
                                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", str(p)],
                               check=True, capture_output=True)
                return Image.open(p).convert("RGB")
        except Exception as e:
            print("could not read first frame of", bg, "->", e)
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=(int(70 + 60 * t), int(120 - 50 * t), int(150 - 20 * t)))
    return img


def composite_still(bg_img, layers, t, darken):
    img = bg_img.convert("RGBA")
    if darken:
        img = Image.blend(img, Image.new("RGBA", img.size, (0, 0, 0, 255)), darken)
    for l in layers:
        if l["start"] <= t < l["end"]:
            x, y = l["pos"]
            off = ANIM_OFFSET.get(l.get("anim"))
            if off and l["fin"]:
                pr = min(1.0, max(0.0, (t - l["start"]) / l["fin"]))
                x, y = int(x + off[0] * (1 - pr) ** 2), int(y + off[1] * (1 - pr) ** 2)
            if (x, y) == tuple(l["pos"]):
                img.alpha_composite(l["img"], dest=(x, y))
            else:
                img.paste(l["img"], (x, y), l["img"])
    return img.convert("RGB")


# ----------------------------------------------------------------- ffmpeg
QUALITY = {"draft": dict(scale=(720, 1280), preset="ultrafast", crf=27),
           "standard": dict(scale=None, preset="veryfast", crf=21),
           "high": dict(scale=None, preset="medium", crf=18)}
GPU_ENCODERS = {"h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"],
                "h264_qsv": ["-c:v", "h264_qsv", "-global_quality", "23"],
                "h264_amf": ["-c:v", "h264_amf", "-quality", "speed"]}
_gpu = {"enc": None, "broken": False}
_PROGRESS_KEYS = ("frame=", "fps=", "stream_", "bitrate=", "total_size=", "out_time", "dup_frames=", "drop_frames=",
                  "speed=", "progress=")


def gpu_encoder():
    if _gpu["broken"] or not FFMPEG:
        return None
    if _gpu["enc"] is None:
        try:
            out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        except Exception:
            out = ""
        _gpu["enc"] = next((c for c in GPU_ENCODERS if c in out), "")
    return _gpu["enc"] or None


def render_video(bg, layers, total, darken, out, quality="standard", gpu=False, progress=None):
    q = QUALITY.get(quality, QUALITY["standard"])
    with tempfile.TemporaryDirectory() as td:
        inputs = []
        fc = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
              + (f",lutyuv=y='val*{1 - darken:.3f}'" if darken else "") + "[v0]"]
        for i, l in enumerate(layers, 1):
            p = Path(td) / f"l{i}.png"
            l["img"].save(p, compress_level=1)
            # each overlay is a small cropped PNG that is only read during its own time window
            dur = max(0.2, l["end"] - l["start"]) + 0.2
            inputs += ["-itsoffset", f"{l['start']:.3f}", "-framerate", str(FPS), "-loop", "1", "-t", f"{dur:.3f}", "-i", str(p)]
            chain = f"[{i}:v]format=rgba"
            if l["fin"]:
                chain += f",fade=t=in:st={l['start']:.3f}:d={l['fin']}:alpha=1"
            if l["fout"]:
                chain += f",fade=t=out:st={l['end'] - l['fout']:.3f}:d={l['fout']}:alpha=1"
            fc.append(f"{chain}[o{i}]")
            x, y = l["pos"]
            off = ANIM_OFFSET.get(l.get("anim"))
            if off and l["fin"]:
                e = f"pow(1-min(1,max(0,(t-{l['start']:.3f})/{l['fin']:.3f})),2)"
                ox = f"x='{x}+({off[0]})*{e}'" if off[0] else f"x={x}"
                oy = f"y='{y}+({off[1]})*{e}'" if off[1] else f"y={y}"
                fc.append(f"[v{i-1}][o{i}]overlay={ox}:{oy}:enable='between(t,{l['start']:.3f},{l['end']:.3f})'[v{i}]")
            else:
                fc.append(f"[v{i-1}][o{i}]overlay={x}:{y}:enable='between(t,{l['start']:.3f},{l['end']:.3f})'[v{i}]")
        last = f"v{len(layers)}"
        if q["scale"]:
            fc.append(f"[{last}]scale={q['scale'][0]}:{q['scale'][1]}[vo]")
            last = "vo"

        def run(venc):
            cmd = ([FFMPEG, "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-stream_loop", "-1", "-i", str(bg)]
                   + inputs + ["-filter_complex", ";".join(fc), "-map", f"[{last}]", "-t", f"{total:.3f}"] + venc
                   + ["-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-movflags", "+faststart", str(out)])
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            err = []
            for line in proc.stdout:
                line = line.strip()
                if line.startswith(("out_time_us=", "out_time_ms=")):
                    try:
                        if progress:
                            progress(min(1.0, int(line.split("=")[1]) / 1e6 / total))
                    except ValueError:
                        pass
                elif line and not line.startswith(_PROGRESS_KEYS):
                    err.append(line)
            if proc.wait():
                raise RuntimeError("\n".join(err[-6:]) or "ffmpeg failed")

        enc = gpu_encoder() if gpu else None
        if enc:
            try:
                return run(GPU_ENCODERS[enc])
            except RuntimeError:
                _gpu["broken"] = True  # no usable GPU encoder -> CPU from now on
        run(["-c:v", "libx264", "-preset", q["preset"], "-crf", str(q["crf"])])


# ----------------------------------------------------------------- data loading
def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def load_templates():
    return {t["id"]: t for t in load_json(ROOT / "templates" / "templates.json")["templates"]}


def load_brand():
    p = ROOT / "brand.json"
    return load_json(p) if p.exists() else {}


def load_content(path):
    p = Path(path)
    if p.suffix.lower() == ".csv":  # columns: id,template,header,lines (separate lines with |),background,tags,cta
        rows = []
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            r["lines"] = [x.strip() for x in r.get("lines", "").split("|") if x.strip()]
            r["tags"] = [x.strip() for x in r.get("tags", "").split(",") if x.strip()]
            rows.append(r)
        return rows
    data = load_json(p)
    return data["videos"] if isinstance(data, dict) else data


# ----------------------------------------------------------------- commands
def cmd_list(a):
    cats = {}
    for t in load_templates().values():
        cats.setdefault(t["category"], []).append(t)
    for c, ts in cats.items():
        print(f"\n== {c} ==")
        for t in ts:
            print(f"  {t['id']:<24} {t['name']}")


def cmd_gallery(a):
    out = ROOT / "output" / "gallery"
    out.mkdir(parents=True, exist_ok=True)
    bgs = list_bgs()
    bg_img = still_background(bgs[0] if bgs else None)
    thumbs = []
    for t in load_templates().values():
        item = t.get("sample", {})
        layers, total, still = build(item, t, load_brand())
        img = composite_still(bg_img, layers, still, {**DEFAULT_TPL, **t}["darken"])
        img.save(out / f"{t['id']}.png")
        thumbs.append((t, img))
        print("preview:", out / f"{t['id']}.png")
    cols, tw, th, lab = 3, 360, 640, 56
    rows = -(-len(thumbs) // cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + lab)), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    f = load_font("Poppins-Medium.ttf", 22)
    for i, (t, img) in enumerate(thumbs):
        x, y = (i % cols) * tw, (i // cols) * (th + lab)
        sheet.paste(img.resize((tw, th)), (x, y))
        d.text((x + 10, y + th + 6), t["id"], font=f, fill=(255, 255, 255))
        d.text((x + 10, y + th + 32), t["category"], font=load_font("Poppins-Regular.ttf", 16), fill=(170, 170, 180))
    sheet.save(out / "_contact_sheet.png")
    print("contact sheet:", out / "_contact_sheet.png")


def items_to_do(a):
    items = load_content(a.content)
    return [(i, it) for i, it in enumerate(items) if not a.id or it["id"] == a.id]


def cmd_preview(a):
    templates, bgs = load_templates(), list_bgs()
    out = ROOT / "output" / "previews"
    out.mkdir(parents=True, exist_ok=True)
    for idx, item in items_to_do(a):
        tpl = templates[item["template"]]
        layers, total, still = build(item, tpl, load_brand())
        bg = pick_bg(item, bgs, idx, a.bg) if (bgs or a.bg) else None
        img = composite_still(still_background(bg), layers, still, {**DEFAULT_TPL, **tpl}["darken"])
        img.save(out / f"{item['id']}.png")
        print(f"preview {item['id']}  ({total:.1f}s)  ->", out / f"{item['id']}.png")


def render_item(item, idx, templates, bgs, force=False, override=None, quality="standard", gpu=False, progress=None, tpl_override=None):
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{item['id']}.mp4"
    if out.exists() and not force:
        print("skip (exists):", out.name)
        return None
    tpl = tpl_override or templates[item["template"]]
    layers, total, _ = build(item, tpl, load_brand())
    bg = pick_bg(item, bgs, idx, override)
    t = time.time()
    render_video(bg, layers, total, {**DEFAULT_TPL, **tpl}["darken"], out, quality, gpu, progress)
    print(f"done {out.name}  {total:.1f}s  bg={bg.name}  ({time.time() - t:.0f}s to render)")
    return out


def cmd_render(a):
    templates, bgs = load_templates(), list_bgs()
    for idx, item in items_to_do(a):
        render_item(item, idx, templates, bgs, a.force, a.bg, a.quality, a.gpu)


def cmd_watch(a):
    """New background in inbox/ -> render the next content item that has no MP4 yet."""
    state_f = ROOT / "inbox" / ".processed.json"
    seen = set(load_json(state_f)) if state_f.exists() else set()
    templates = load_templates()
    print("Watching inbox/ ... Ctrl+C to stop.")
    while True:
        for bg in list_bgs():
            if bg.name in seen:
                continue
            time.sleep(2)  # let the copy finish
            pending = [(i, it) for i, it in enumerate(load_content(a.content))
                       if not (ROOT / "output" / f"{it['id']}.mp4").exists()]
            if not pending:
                print("No pending content items left; add more to", a.content)
                break
            i, it = pending[0]
            print(f"new background {bg.name} -> {it['id']}")
            render_item(it, i, templates, list_bgs(), True, bg)
            seen.add(bg.name)
            state_f.write_text(json.dumps(sorted(seen)))
        time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "gallery", "preview", "render", "watch"])
    ap.add_argument("--content", default=str(ROOT / "content" / "ideas.json"))
    ap.add_argument("--id")
    ap.add_argument("--bg")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--quality", choices=list(QUALITY), default="standard")
    ap.add_argument("--gpu", action="store_true", help="use NVENC/QSV/AMF if available")
    a = ap.parse_args()
    if a.cmd in ("render", "watch", "gallery", "preview"):
        ensure_ffmpeg()
    if not FFMPEG and a.cmd in ("render", "watch", "gallery", "preview"):
        sys.exit("FFmpeg not found. Run: pip install imageio-ffmpeg   (or install FFmpeg and reopen the terminal)")
    {"list": cmd_list, "gallery": cmd_gallery, "preview": cmd_preview,
     "render": cmd_render, "watch": cmd_watch}[a.cmd](a)


if __name__ == "__main__":
    main()
