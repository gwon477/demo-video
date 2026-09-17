"""M3 on the sample app: hash cache (FR-050), one-scene re-render after a subtitle edit (SC-003),
draft mode (FR-052), template intro/outro clips, full compose + verify (SC-002 timing).

Set DV_SKIP_BROWSER=1 to skip.
"""
import http.server
import json
import os
import shutil
import threading
import time
import unittest

from helpers import REPO, ProjectCase, dv

SAMPLE = REPO / "examples" / "sample-app"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@unittest.skipIf(os.environ.get("DV_SKIP_BROWSER") == "1" or shutil.which("playwright-cli") is None, "browser tests skipped")
class CacheDraftTest(ProjectCase):
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
        sb = json.loads((SAMPLE / "demo" / "storyboard.json").read_text())
        sb["scenes"] = [sc for sc in sb["scenes"] if sc["id"] in ("01-dashboard-fail", "05-board-edit")]
        sb["scenes"][1]["transitionIn"] = {"type": "fade", "ms": 400}
        self.write_json("demo/storyboard.json", sb)
        shutil.copy(SAMPLE / "demo" / "survey.json", self.demo / "survey.json")
        cfg = json.loads((SAMPLE / "demo" / "config.json").read_text())
        cfg["app"]["url"] = self.url
        self.write_json("demo/config.json", cfg)
        dv("approve", "storyboard", cwd=self.project)

    def test_cache_single_rerender_draft_and_full_pipeline(self):
        t0 = time.time()
        code, out, err = dv("render", "--close", cwd=self.project)
        self.assertEqual(code, 0, out + err)
        self.assertIn("4 scene(s) rendered, 0 cached", out)
        for sid in ("00-intro", "01-dashboard-fail", "05-board-edit", "99-outro"):
            self.assertTrue((self.demo / "scenes" / f"{sid}.webm").exists(), sid)

        # FR-050: nothing changed -> nothing recorded
        code, out, err = dv("render", "--close", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("4 scene(s) up to date", out)

        # SC-003: edit one subtitle -> only that scene is re-recorded
        sb = self.read_json("demo/storyboard.json")
        sb["scenes"][1]["steps"][0]["subtitle"]["text"] = "이름은 더블클릭 한 번으로 고칩니다"
        self.write_json("demo/storyboard.json", sb)
        dv("validate", "--fix", cwd=self.project)
        dv("approve", "storyboard", cwd=self.project)
        code, out, err = dv("render", "--close", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("1 scene(s) rendered, 3 cached", out)
        self.assertIn("05-board-edit", out)

        # compose + verify on the full-size clips
        code, out, err = dv("compose", cwd=self.project)
        self.assertEqual(code, 0, err)
        code, out, err = dv("verify", cwd=self.project)
        self.assertEqual(code, 0, out + err)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 600, "SC-002: render+compose must finish within 10 minutes")

        # FR-052: draft clips are 960 wide and live apart from the full-size ones
        code, out, err = dv("render", "--draft", "--close", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("(960x540 draft)", out)
        self.assertTrue((self.demo / "scenes" / "draft" / "01-dashboard-fail.webm").exists())
        code, out, err = dv("compose", "--draft", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_json("demo/manifest-draft.json")["resolution"], "960x540")
        code, out, err = dv("verify", "--draft", cwd=self.project)
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
