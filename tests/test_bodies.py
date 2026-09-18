"""Hand-written body lifecycle: dv.py body --hand / --mark, @scene drift check in render, styles --set."""
import json
import sys
import unittest

from helpers import REPO, ProjectCase, dv

sys.path.insert(0, str(REPO / "skills" / "demo-video" / "scripts"))
from lib import bodygen, tts  # noqa: E402

SB = {
    "schemaVersion": 2, "meta": {"name": "t", "size": [640, 360]},
    "intro": {"source": "html", "template": "default", "title": "T", "holdMs": 2000},
    "outro": {"source": "html", "template": "default", "title": "T", "cta": "go", "holdMs": 2000},
    "scenes": [{"id": "01-a", "url": "/a", "waitFor": "#x", "transitionIn": {"type": "fade", "ms": 400}, "dwellMs": 4000,
                "steps": [{"subtitle": {"text": "첫 자막", "hook": True}, "actions": [{"type": "click", "target": "#b"}], "holdMs": 3000}]}],
}


class SceneHashTest(unittest.TestCase):
    def test_hash_ignores_timing_but_not_actions(self):
        a = json.loads(json.dumps(SB["scenes"][0]))
        b = json.loads(json.dumps(a)); b["dwellMs"] = 9000; b["steps"][0]["holdMs"] = 5000
        self.assertEqual(bodygen.scene_hash(a), bodygen.scene_hash(b))
        c = json.loads(json.dumps(a)); c["steps"][0]["actions"].append({"type": "zoomOut"})
        self.assertNotEqual(bodygen.scene_hash(a), bodygen.scene_hash(c))

    def test_hand_body_carries_marker_and_statements(self):
        text = bodygen.hand_body(SB["scenes"][0])
        self.assertTrue(text.startswith("// @scene " + bodygen.scene_hash(SB["scenes"][0])))
        self.assertFalse(bodygen.is_generated(text))
        self.assertIn("await subtitleSpan(\"첫 자막\"", text)
        self.assertIn("await click(\"#b\");", text)


class BodyCommandTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write_json("demo/storyboard.json", SB)
        dv("approve", "storyboard", cwd=self.project)

    def test_hand_body_then_drift_then_mark(self):
        code, out, _ = dv("body", "01-a", "--hand", cwd=self.project)
        self.assertEqual(code, 0)
        self.assertIn("hand-written", out)
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)
        # storyboard scene changes -> render refuses until the body is reconciled
        sb = self.read_json("demo/storyboard.json")
        sb["scenes"][0]["steps"][0]["actions"].append({"type": "zoomOut"})
        self.write_json("demo/storyboard.json", sb)
        dv("approve", "storyboard", cwd=self.project)
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("out of date", err)
        code, out, _ = dv("body", "01-a", "--mark", cwd=self.project)
        self.assertEqual(code, 0)
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)

    def test_missing_marker_only_warns(self):
        (self.demo / "scenes").mkdir(exist_ok=True)
        (self.demo / "scenes" / "01-a.body.js").write_text("await page.goto(BASE + '/a');\n// ---record---\nawait subtitleSpan('첫 자막', HOLD[0], null);\n")
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("no @scene marker", err)

    def test_body_back_to_generated(self):
        dv("body", "01-a", "--hand", cwd=self.project)
        code, out, _ = dv("body", "01-a", cwd=self.project)
        self.assertEqual(code, 0)
        self.assertTrue((self.demo / "scenes" / "01-a.body.js").read_text().startswith("// @generated"))


class StylesSetTest(ProjectCase):
    def test_set_writes_typed_values(self):
        code, out, err = dv("styles", "--set", "subtitle.color=#ffffff,subtitle.fontSizeRatio=0.04,highlight.borderPx=3", cwd=self.project)
        self.assertEqual(code, 0, err)
        t = self.read_json("demo/theme.json")
        self.assertEqual(t["subtitle"]["color"], "#ffffff")
        self.assertEqual(t["subtitle"]["fontSizeRatio"], 0.04)
        self.assertEqual(t["highlight"]["borderPx"], 3)

    def test_set_rejects_unknown_key(self):
        code, _, err = dv("styles", "--set", "subtitle.colour=#fff", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("unknown key", err)



class NarrateTest(ProjectCase):
    def test_dry_run_estimates_and_refuses_when_off(self):
        self.write_json("demo/storyboard.json", SB)
        self.write_json("demo/config.json", {"app": {"url": "http://x"}, "narration": {"provider": "none"}})
        code, _, err = dv("narrate", "--dry-run", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("narration is off", err)
        code, out, err = dv("narrate", "--dry-run", "--provider", "say", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("1 lines", out)
        self.assertIn("--dry-run", out)
        self.assertEqual(self.read_json("demo/storyboard.json"), SB, "dry run must not touch the storyboard")

    def test_edge_text_strips_markup(self):
        self.assertEqual(tts.edge_text("기간을 바꾸면[[slnc 300]] [[emph +]]그래프[[emph -]]가 갱신됩니다"), "기간을 바꾸면, 그래프가 갱신됩니다")
        self.assertEqual(tts.spoken_text("[[rate 120]]오류 3건"), "오류 3건")


if __name__ == "__main__":
    unittest.main()
