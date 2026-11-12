"""Fast tests: no FFmpeg, no browser. Run: python -m unittest discover -s tests"""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import render as R  # noqa: E402
import studio as ST  # noqa: E402

TPLS = R.load_templates()
BRAND = R.load_brand()


def item(template="stack_test", **kw):
    base = {"id": "t", "template": next(iter(TPLS)), "header": "Test headline", "lines": ["One", "Two", "Three"]}
    base.update(kw)
    return base


class Build(unittest.TestCase):
    def test_every_layout_builds_its_sample(self):
        for tid, t in TPLS.items():
            s = t.get("sample") or {"header": "Hello", "lines": ["a", "b"]}
            layers, total, still = R.build({"id": "s", "template": tid, **s}, t, BRAND)
            self.assertTrue(layers, tid)
            self.assertGreater(total, 0)
            for l in layers:
                self.assertLessEqual(l["start"], l["end"], tid)

    def test_overrides_size_color_offset(self):
        t = TPLS[next(iter(TPLS))]
        plain, *_ = R.build(item(), t, BRAND)
        v = item(lines=[{"text": "One", "size": 60, "dx": 30, "dy": 20, "color": "#FF0000"}, "Two", "Three"])
        over, *_ = R.build(v, t, BRAND)
        pl = next(l for l in plain if l["kind"] == "line" and l["idx"] == 0)
        ol = next(l for l in over if l["kind"] == "line" and l["idx"] == 0)
        self.assertEqual(ol["size"], 60)
        self.assertNotEqual(pl["pos"], ol["pos"])

    def test_delay_show_and_anim(self):
        t = {**TPLS[next(iter(TPLS))], "mode": "stack"}
        v = item(lines=[{"text": "One", "delay": 1.0, "show": 1.5, "anim": "slide_up"}, "Two"])
        layers, *_ = R.build(v, t, BRAND)
        l0 = next(l for l in layers if l["kind"] == "line" and l["idx"] == 0)
        base, *_ = R.build(item(lines=["One", "Two"]), t, BRAND)
        b0 = next(l for l in base if l["kind"] == "line" and l["idx"] == 0)
        self.assertAlmostEqual(l0["start"] - b0["start"], 1.0, places=2)
        self.assertAlmostEqual(l0["end"] - l0["start"], 1.5, places=2)
        self.assertEqual(l0["anim"], "slide_up")

    def test_glow_extends_bounds_and_opacity_lowers_alpha(self):
        t = TPLS[next(iter(TPLS))]
        a, *_ = R.build(item(header_style={"bg_mode": "none"}), t, BRAND)
        b, *_ = R.build(item(header_style={"bg_mode": "none", "glow_color": "#FF2FA0", "glow_r": 24}), t, BRAND)
        ha, hb = (next(l for l in x if l["kind"] == "header") for x in (a, b))
        self.assertGreater(hb["img"].width * hb["img"].height, ha["img"].width * ha["img"].height)
        c, *_ = R.build(item(header_style={"opacity": 0.4}), t, BRAND)
        hc = next(l for l in c if l["kind"] == "header")
        self.assertLessEqual(hc["img"].getchannel("A").getextrema()[1], 255 * 0.4 + 1)

    def test_still_composite_without_ffmpeg(self):
        t = TPLS[next(iter(TPLS))]
        layers, total, still = R.build(item(), t, BRAND)
        img = R.composite_still(R.still_background(None), layers, still, 0.2)
        self.assertEqual(img.size, (R.W, R.H))


class Studio(unittest.TestCase):
    def test_presets_are_valid(self):
        p = ST.read_presets()
        files = set(ST.list_fonts())
        for f in p["fonts"]:
            self.assertIn(f["file"], files)
        for s in p["styles"]:
            self.assertIn(s["style"]["font"], files, s["id"])
            self.assertFalse(set(s["style"]) - ST.ELEMENT_KEYS, s["id"])

    def test_preset_conversion(self):
        neon = ST.preset_by_id("neon_pink")["style"]
        t = ST.flat_to_template_style(neon)
        self.assertEqual(t["glow"]["color"], "#FF2FA0")
        self.assertIsNone(t.get("bg"))
        box = ST.flat_to_template_style(ST.preset_by_id("strong_yellow")["style"])
        self.assertEqual(box["bg"]["mode"], "line")

    def test_apply_preset_resets_visual_keys(self):
        o = ST.apply_preset_flat({"text": "x", "glow_color": "#fff", "size": 70}, ST.preset_by_id("classic")["style"])
        self.assertNotIn("glow_color", o)
        self.assertEqual(o["size"], 70)
        self.assertEqual(o["text"], "x")

    def test_sheet_mapping(self):
        table = ST.parse_rows("Hook,Line 1,Line 2,Tags,Status\nHi there,One,Two | x,amsterdam,verify\n,skip,me,,\n")
        vids = ST.table_to_videos(table, default_layout=next(iter(TPLS)))
        self.assertEqual(len(vids), 1)
        v = vids[0]
        self.assertEqual(v["header"], "Hi there")
        self.assertEqual(v["lines"], ["One", "Two\nx"])
        self.assertEqual(v["tags"], ["amsterdam"])
        self.assertEqual(v["status"], "verify")

    def test_sheet_body_column_and_tsv(self):
        table = ST.parse_rows("Title\tBody\nHello\tone\ntwo\n")  # quoted newlines not present: 2nd row 'two' becomes its own (blank title) row
        self.assertEqual(table["headers"], ["Title", "Body"])
        vids = ST.table_to_videos(ST.parse_rows('Title,Body\nHello,"one\ntwo"\n'), default_layout=next(iter(TPLS)))
        self.assertEqual(vids[0]["lines"], ["one", "two"])

    def test_merge_imported_skip_and_update(self):
        videos = [{"id": "a", "template": "x", "header": "Hello", "lines": ["old"]}]
        new = [{"id": "hello", "template": "x", "header": "hello", "lines": ["new"]}, {"id": "b", "template": "x", "header": "B", "lines": ["1"]}]
        self.assertEqual(ST.merge_imported(json.loads(json.dumps(videos)), json.loads(json.dumps(new)), "skip"), (1, 0, 1))
        v2 = json.loads(json.dumps(videos))
        self.assertEqual(ST.merge_imported(v2, json.loads(json.dumps(new)), "update"), (1, 1, 0))
        self.assertEqual(v2[0]["lines"], ["new"])

    def test_validate_video_errors(self):
        with self.assertRaises(ValueError):
            ST.validate_video({"template": "nope", "header": "x"})
        with self.assertRaises(ValueError):
            ST.validate_video({"template": next(iter(TPLS))})
        v, warn = ST.validate_video({"template": next(iter(TPLS)), "header": "x", "lines": [{"text": "a", "bogus": 1}]})
        self.assertTrue(warn)


if __name__ == "__main__":
    unittest.main()
