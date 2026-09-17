"""M3: compose and verify on synthetic clips (ffmpeg only, no browser)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import REPO, ProjectCase, dv

sys.path.insert(0, str(REPO / "skills" / "demo-video" / "scripts"))
from lib import compose as C  # noqa: E402

W, H = 640, 360


def make_clip(path: Path, seconds: float, color=None, size=(W, H), rate=25):
    src = f"color=c={color}:size={size[0]}x{size[1]}:rate={rate}" if color else f"testsrc=size={size[0]}x{size[1]}:rate={rate}"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src, "-t", f"{seconds}",
                    "-c:v", "libvpx", "-b:v", "1M", "-pix_fmt", "yuv420p", str(path)], check=True)


def make_mp4(path: Path, seconds: float, size):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size[0]}x{size[1]}:rate=30",
                    "-t", f"{seconds}", "-pix_fmt", "yuv420p", str(path)], check=True)


def make_tone(path: Path, seconds=8.0):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}",
                    "-af", "volume=0.2", str(path)], check=True)


def make_speech(path: Path, seconds=1.2):
    """A stand-in narration line: a 660Hz tone."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=660:duration={seconds}",
                    "-af", "volume=0.5", str(path)], check=True)


class DuckExpressionTest(unittest.TestCase):
    def test_merge_ranges(self):
        self.assertEqual(C.merge_ranges([(0, 1), (1.2, 2), (5, 6)]), [[0, 2], [5, 6]])

    def test_expression_shape(self):
        e = C.duck_expression([(2.0, 3.0)], -18, 300, 800)
        self.assertIn("clip((t-(1.700))/0.300,0,1)", e)
        self.assertIn("clip(((3.800)-t)/0.800,0,1)", e)
        self.assertTrue(e.startswith("1-(1-0.1259)*"))
        self.assertEqual(C.duck_expression([], -18, 300, 800), "1")


class ComposeVerifyTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.scenes = self.demo / "scenes"
        self.scenes.mkdir()
        self.sb = {
            "schemaVersion": 2, "meta": {"name": "syn", "size": [W, H]},
            "intro": {"source": "html", "template": "default", "title": "T", "holdMs": 2000},
            "outro": {"source": "html", "template": "default", "title": "T", "cta": "go", "holdMs": 2000},
            "scenes": [
                {"id": "01-a", "url": "/a", "transitionIn": {"type": "fade", "ms": 400}, "dwellMs": 3000,
                 "steps": [{"subtitle": {"text": "첫 자막", "hook": True}, "actions": [], "holdMs": 2000}]},
                {"id": "02-b", "url": "/a", "transitionIn": {"type": "cut"}, "dwellMs": 3000,
                 "steps": [{"subtitle": {"text": "둘째 자막"}, "actions": [], "holdMs": 2000}]},
            ],
        }
        self.write_json("demo/storyboard.json", self.sb)
        self.write_json("demo/config.json", {"app": {"url": "http://x"}, "bgm": {"source": "none"}})
        make_clip(self.scenes / "00-intro.webm", 2.0, color="0x0b1220")
        make_clip(self.scenes / "01-a.webm", 3.0)
        make_clip(self.scenes / "02-b.webm", 3.0)
        make_clip(self.scenes / "99-outro.webm", 2.0, color="0x0b1220")
        for sid, text in (("01-a", "첫 자막"), ("02-b", "둘째 자막")):
            self.write_json(f"demo/scenes/{sid}.timing.json",
                            {"sceneId": sid, "cues": [{"text": text, "startMs": 200, "endMs": 2200}], "marks": []})

    def test_compose_lengths_and_srt(self):
        code, out, err = dv("compose", cwd=self.project)
        self.assertEqual(code, 0, err)
        m = self.read_json("demo/manifest.json")
        # 2 + 3 + 3 + 2 - (0.4 intro->01) - (0.04 cut) - (0.4 outro)
        self.assertAlmostEqual(m["durationSec"], 10 - 0.4 - 0.04 - 0.4, delta=0.1)
        self.assertEqual([s["id"] for s in m["scenes"]], ["00-intro", "01-a", "02-b", "99-outro"])
        srt = (self.demo / "output" / "syn.srt").read_text()
        self.assertIn("첫 자막", srt)
        self.assertIn("둘째 자막", srt)
        self.assertTrue((self.demo / "output" / "syn.mp4").exists())
        code, out, err = dv("verify", cwd=self.project)
        self.assertEqual(code, 0, out + err)

    def test_review_packet_and_missing_effect(self):
        dv("compose", cwd=self.project)
        code, out, err = dv("review", "--json", cwd=self.project)
        self.assertEqual(code, 0, err)
        rep = json.loads(out)
        self.assertEqual([s["id"] for s in rep["scenes"]], ["00-intro", "01-a", "02-b", "99-outro"])
        self.assertTrue((self.demo / "output" / "review" / "01-a.png").exists())
        self.assertTrue((self.demo / "output" / "review-transitions.png").exists())
        self.assertEqual(len(rep["boundaries"]), 3)
        # a zoom in the storyboard with no zoomIn mark recorded is a fail
        self.sb["scenes"][0]["steps"][0]["actions"] = [{"type": "zoom", "target": "#x"}, {"type": "zoomOut"}]
        self.write_json("demo/storyboard.json", self.sb)
        code, out, err = dv("review", "--json", cwd=self.project)
        self.assertEqual(code, 1)
        rep = json.loads(out)
        self.assertTrue(any(f["kind"] == "effect" and f["severity"] == "fail" for f in rep["findings"]))

    def test_verify_fails_on_black_frame(self):
        make_clip(self.scenes / "02-b.webm", 3.0, color="black")
        dv("compose", cwd=self.project)
        code, out, err = dv("verify", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("black frame", err)

    def test_user_intro_video_is_letterboxed(self):
        make_mp4(self.project / "intro43.mp4", 2.0, (320, 240))
        self.sb["intro"] = {"source": "video", "path": str(self.project / "intro43.mp4")}
        self.write_json("demo/storyboard.json", self.sb)
        code, out, err = dv("compose", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertTrue(any("letterboxed" in n for n in self.read_json("demo/manifest.json")["notes"]))
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(self.demo / "output" / "syn.mp4")], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), f"{W},{H}")

    def test_bgm_probe_compose_loudness(self):
        make_tone(self.project / "tone.wav")
        code, out, err = dv("bgm", "probe", str(self.project / "tone.wav"), cwd=self.project)
        self.assertEqual(code, 0, err)
        cfg = self.read_json("demo/config.json")
        self.assertEqual(cfg["bgm"]["source"], "file")
        self.assertAlmostEqual(cfg["bgm"]["durationSec"], 8.0, delta=0.1)
        code, out, err = dv("compose", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("bgm: tone.wav", out)
        code, out, err = dv("verify", "--json", cwd=self.project)
        rep = json.loads(out)
        self.assertTrue(rep["ok"], rep["failures"])
        lufs = next(c for c in rep["checks"] if c["check"] == "loudness")["integratedLufs"]
        self.assertAlmostEqual(lufs, -16, delta=1.0)

    def test_narration_is_placed_and_bgm_ducked(self):
        make_tone(self.project / "tone.wav")
        dv("bgm", "probe", str(self.project / "tone.wav"), cwd=self.project)
        (self.demo / "audio").mkdir()
        make_speech(self.demo / "audio" / "01-a-0.aiff")
        self.write_json("demo/narration-syn.json", {"voice": "test", "rate": 150, "padMs": 400,
                                                    "lines": [{"sceneId": "01-a", "index": 0, "text": "첫 자막",
                                                               "file": "audio/01-a-0.aiff", "durationMs": 1200}]})
        code, out, err = dv("compose", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("duck -18 dB under 1 lines", out)
        self.assertIn("adelay=1800|1800", out)      # intro 2.0s - 0.4s fade + cue 0.2s
        code, out, err = dv("compose", cwd=self.project)
        self.assertEqual(code, 0, err)
        code, out, err = dv("verify", "--json", cwd=self.project)
        rep = json.loads(out)
        self.assertTrue(rep["ok"], rep["failures"])
        cue = next(c for c in rep["checks"] if c["check"] == "narrationCue")
        self.assertGreater(cue["maxVolumeDb"], -30)

    def test_draft_compose_uses_cuts_and_no_audio(self):
        make_tone(self.project / "tone.wav")
        dv("bgm", "probe", str(self.project / "tone.wav"), cwd=self.project)
        draft = self.scenes / "draft"
        draft.mkdir()
        for sid in ("00-intro", "01-a", "02-b", "99-outro"):
            make_clip(draft / f"{sid}.webm", 2.0, size=(320, 180))
        code, out, err = dv("compose", "--draft", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("0.00s transitions", out)
        self.assertNotIn("bgm:", out)
        m = self.read_json("demo/manifest-draft.json")
        self.assertEqual(m["name"], "syn-draft")
        self.assertEqual(m["resolution"], "320x180")


if __name__ == "__main__":
    unittest.main()
