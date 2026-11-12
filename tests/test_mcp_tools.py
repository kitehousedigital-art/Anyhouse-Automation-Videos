"""MCP tool functions called directly against a temp copy of the data files (needs `pip install mcp`)."""
import json, shutil, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "mcp_server")]
import studio as ST  # noqa: E402

try:
    import anyhouse_mcp as M  # noqa: E402
except ModuleNotFoundError as e:  # mcp not installed
    M = None
    _err = e


@unittest.skipIf(M is None, "mcp package not installed")
class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "content" / "ideas.json", self.tmp / "ideas.json")
        shutil.copy(ROOT / "templates" / "templates.json", self.tmp / "templates.json")
        self._old = (ST.CONTENT, ST.TEMPLATES)
        ST.CONTENT, ST.TEMPLATES = self.tmp / "ideas.json", self.tmp / "templates.json"
        self.layout = ST.read_templates()[0]["id"]

    def tearDown(self):
        ST.CONTENT, ST.TEMPLATES = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_crud_and_style(self):
        r = M.upsert_video({"header": "Hello MCP", "template": self.layout, "lines": ["A | B", "C"]})
        vid = r["saved"]["id"]
        self.assertEqual(r["saved"]["lines"][0], "A\nB")
        M.style_element(vid, "header", preset="neon_pink")
        M.style_element(vid, "line:1", style={"color": "#FFD21F", "anim": "slide_up"})
        v = M.get_video(vid)
        self.assertEqual(v["header_style"]["glow_color"], "#FF2FA0")
        self.assertEqual(v["lines"][1]["anim"], "slide_up")
        M.style_element(vid, "all", clear=True)
        v = M.get_video(vid)
        self.assertNotIn("header_style", v)
        self.assertEqual(v["lines"], ["A\nB", "C"])
        d = M.describe_video(vid)
        self.assertTrue(d["elements"])
        M.update_video(vid, {"interval": 1.5})
        self.assertEqual(M.get_video(vid)["interval"], 1.5)
        M.duplicate_video(vid, "copy")
        self.assertIn("copy", [x["id"] for x in M.list_videos()])
        M.delete_video(vid)
        self.assertNotIn(vid, [x["id"] for x in M.list_videos()])

    def test_errors_are_clear(self):
        with self.assertRaises(ValueError):
            M.upsert_video({"header": "x", "template": "nope"})
        vid = M.upsert_video({"header": "E", "template": self.layout, "lines": ["a"]})["saved"]["id"]
        with self.assertRaises(ValueError):
            M.style_element(vid, "line:5", style={"color": "#fff"})
        with self.assertRaises(ValueError):
            M.style_element(vid, "header", style={"bogus": 1})

    def test_import_sheet_dry_run_then_save(self):
        csv_text = "Headline,Line 1,Line 2\nOne,a,b\nTwo,c,d\n"
        n0 = len(M.list_videos())
        r = M.import_sheet(csv_text=csv_text, layout=self.layout)
        self.assertTrue(r["dry_run"])
        self.assertEqual(len(M.list_videos()), n0)
        r = M.import_sheet(csv_text=csv_text, layout=self.layout, dry_run=False)
        self.assertEqual(r["added"], 2)
        self.assertEqual(len(M.list_videos()), n0 + 2)

    def test_layout_style(self):
        M.set_layout_style(self.layout, "header", "strong_yellow")
        self.assertEqual(M.get_layout(self.layout)["header"]["bg"]["color"], "#FFD21F")

    def test_preview_returns_image(self):
        vid = M.list_videos()[0]["id"]
        out = M.preview_frame(vid, width=270)
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
