"""M2 completion criteria on the sample app (needs playwright-cli, a browser and ffmpeg).

- zoom and scroll: the subtitle box keeps its position and size (SC-004)
- pointer and html5 drag reorder the lists; file drop lands (waitFor in the storyboard asserts the app state)
- bodies are generated from the storyboard; timing.json carries cues and marks

Set DV_SKIP_BROWSER=1 to skip.
"""
import http.server
import json
import os
import shutil
import subprocess
import threading
import unittest
from pathlib import Path

from helpers import REPO, ProjectCase, dv

SAMPLE = REPO / "examples" / "sample-app"
SCENES = ["01-dashboard-fail", "02-dashboard-log", "04-board-drag", "06-board-html5", "07-upload-drop"]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def gray_frame(webm: Path, at_ms: int, w: int, h: int) -> bytes:
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at_ms / 1000:.3f}", "-i", str(webm), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    assert len(r.stdout) >= w * h, f"no frame at {at_ms}ms"
    return r.stdout[: w * h]


def subtitle_bbox(frame: bytes, w: int, h: int):
    """Bounding box of the dark subtitle box in the bottom 20% of the frame."""
    rows = []
    for y in range(int(h * 0.8), h):
        row = frame[y * w:(y + 1) * w]
        dark = sum(1 for v in row if v < 120)
        if dark > w * 0.12:
            rows.append(y)
    assert rows, "no subtitle box found"
    y0, y1 = rows[0], rows[-1]
    cols = []
    for x in range(w):
        dark = sum(1 for y in range(y0, y1 + 1, 2) if frame[y * w + x] < 120)
        if dark > (y1 - y0) * 0.3:
            cols.append(x)
    return (cols[0], y0, cols[-1], y1)


@unittest.skipIf(os.environ.get("DV_SKIP_BROWSER") == "1" or shutil.which("playwright-cli") is None, "browser tests skipped")
class SampleAppRenderTest(ProjectCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: _Quiet(*a, directory=str(SAMPLE), **k))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        super().setUp()
        for name in ("storyboard.json", "survey.json"):
            shutil.copy(SAMPLE / "demo" / name, self.demo / name)
        cfg = json.loads((SAMPLE / "demo" / "config.json").read_text())
        cfg["app"]["url"] = self.url
        self.write_json("demo/config.json", cfg)

    def test_render_regression(self):
        code, _, err = dv("validate", cwd=self.project)
        self.assertEqual(code, 0, err)
        code, _, err = dv("approve", "storyboard", cwd=self.project)
        self.assertEqual(code, 0, err)
        code, out, err = dv("render", *SCENES, "--close", cwd=self.project)
        self.assertEqual(code, 0, out + err)

        sb = self.read_json("demo/storyboard.json")
        w, h = sb["meta"]["size"]
        for sid in SCENES:
            body = (self.demo / "scenes" / f"{sid}.body.js").read_text()
            self.assertTrue(body.startswith("// @generated"), sid)
            self.assertTrue((self.demo / "scenes" / f"{sid}.webm").exists(), sid)
            timing = self.read_json(f"demo/scenes/{sid}.timing.json")
            self.assertEqual(len(timing["cues"]), 1, sid)
            self.assertGreater(timing["cues"][0]["endMs"], timing["cues"][0]["startMs"])

        # marks prove the helpers ran: zoom in/out, scroll, drag in both modes, file drop
        kinds = {sid: [m["type"] for m in self.read_json(f"demo/scenes/{sid}.timing.json")["marks"]] for sid in SCENES}
        self.assertEqual(kinds["01-dashboard-fail"], ["zoomIn", "zoomOut"])
        self.assertIn("scroll", kinds["02-dashboard-log"])
        drags = [m for m in self.read_json("demo/scenes/04-board-drag.timing.json")["marks"] if m["type"] == "drag"]
        self.assertEqual(drags[0]["mode"], "pointer")
        drags = [m for m in self.read_json("demo/scenes/06-board-html5.timing.json")["marks"] if m["type"] == "drag"]
        self.assertEqual(drags[0]["mode"], "html5")
        self.assertIn("dropFile", kinds["07-upload-drop"])
        # (the storyboard's waitFor actions on the order/upload text already failed the render if the app state was wrong)

        # SC-004: the subtitle box does not move or scale while the page is zoomed
        marks = self.read_json("demo/scenes/01-dashboard-fail.timing.json")["marks"]
        zin = next(m for m in marks if m["type"] == "zoomIn")["atMs"]
        zout = next(m for m in marks if m["type"] == "zoomOut")["atMs"]
        webm = self.demo / "scenes" / "01-dashboard-fail.webm"
        self.assertGreater(zout, zin)
        zoomed = subtitle_bbox(gray_frame(webm, zout - 150, w, h), w, h)      # fully zoomed, no highlight dim
        # Reference: an unzoomed frame of the next scene (different text, so compare the
        # geometry that must be text-independent: horizontal center, top, bottom).
        webm2 = self.demo / "scenes" / "02-dashboard-log.webm"
        marks2 = self.read_json("demo/scenes/02-dashboard-log.timing.json")["marks"]
        sc = next(m for m in marks2 if m["type"] == "scroll")["atMs"]
        plain = subtitle_bbox(gray_frame(webm2, 400, w, h), w, h)
        scrolled = subtitle_bbox(gray_frame(webm2, sc - 300, w, h), w, h)   # still scrolling or just settled

        def geom(b):
            return ((b[0] + b[2]) // 2, b[1], b[3])
        for name, box in (("zoom", zoomed), ("scroll", scrolled)):
            for a, b in zip(geom(plain), geom(box)):
                self.assertLessEqual(abs(a - b), 4, f"subtitle box moved under {name}: {plain} vs {box}")
        self.assertEqual(scrolled, plain, "same text, same box expected across the scroll")

    def test_hand_edited_body_is_kept(self):
        dv("approve", "storyboard", cwd=self.project)
        scenes = self.demo / "scenes"
        scenes.mkdir(exist_ok=True)
        (scenes / "01-dashboard-fail.body.js").write_text("await page.goto(BASE + '/index.html');\n// ---record---\n"
                                                          "await subtitleSpan('밤새 돌아간 테스트 중 실패한 3건만 먼저 봅니다', HOLD[0], null);\n")
        code, _, err = dv("render", "01-dashboard-fail", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertFalse((scenes / "01-dashboard-fail.body.js").read_text().startswith("// @generated"))


if __name__ == "__main__":
    unittest.main()
