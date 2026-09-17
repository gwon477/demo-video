"""M1: doctor, init, approve, status and the state.json hash gate."""
import http.server
import json
import threading
import unittest

from helpers import ProjectCase, dv


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _serve(directory):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: _Quiet(*a, directory=directory, **k))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


STORYBOARD = {
    "schemaVersion": 1, "name": "t", "baseUrl": "http://127.0.0.1:1",
    "video": {"width": 640, "height": 360},
    "scenes": [{"id": "01-intro", "kind": "intro", "title": "T", "durationMs": 1000}],
}


class DoctorTest(ProjectCase):
    def test_doctor_json_reports_required_items(self):
        code, out, err = dv("doctor", "--json", "--offline", cwd=self.project)
        self.assertEqual(code, 0, err)
        rep = json.loads(out)
        names = {i["name"] for i in rep["items"]}
        for n in ("python", "node", "playwright-cli", "playwright", "ffmpeg", "ffmpeg filters", "ffmpeg encoders", "tts"):
            self.assertIn(n, names)
        self.assertTrue(rep["ok"])

    def test_doctor_fails_without_ffmpeg(self):
        code, out, _ = dv("doctor", "--json", "--offline", cwd=self.project, env={"PATH": "/nonexistent"})
        self.assertEqual(code, 1)
        rep = json.loads(out)
        self.assertFalse(rep["ok"])
        failed = {i["name"] for i in rep["items"] if i["status"] == "FAIL"}
        self.assertIn("ffmpeg", failed)
        self.assertIn("node", failed)
        fix = next(i["fix"] for i in rep["items"] if i["name"] == "ffmpeg")
        self.assertTrue(fix, "a missing item must come with an install command")


class InitTest(ProjectCase):
    def test_init_writes_config_state_gitignore(self):
        srv, url = _serve(str(self.project))
        try:
            code, out, err = dv("init", "--url", url, "--name", "x", "--size", "1280x720", cwd=self.project)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(code, 0, err)
        cfg = self.read_json("demo/config.json")
        self.assertEqual(cfg["app"]["url"], url)
        self.assertEqual(cfg["video"]["size"], [1280, 720])
        self.assertEqual(self.read_json("demo/state.json")["approvals"], {})
        gi = (self.project / ".gitignore").read_text()
        self.assertIn("demo/output/", gi)
        self.assertIn("demo/.accounts.json", gi)
        self.assertTrue((self.demo / "scenes").is_dir())

    def test_init_fails_when_url_unreachable(self):
        code, _, err = dv("init", "--url", "http://127.0.0.1:1", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("not reachable", err)
        self.assertFalse((self.demo / "config.json").exists())

    def test_init_refuses_overwrite_without_force(self):
        dv("init", "--url", "http://x", "--skip-url-check", cwd=self.project)
        code, _, err = dv("init", "--url", "http://y", "--skip-url-check", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        code, _, _ = dv("init", "--url", "http://y", "--skip-url-check", "--force", cwd=self.project)
        self.assertEqual(code, 0)
        self.assertEqual(self.read_json("demo/config.json")["app"]["url"], "http://y")

    def test_init_rejects_odd_size(self):
        code, _, err = dv("init", "--url", "http://x", "--skip-url-check", "--size", "1281x720", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("even", err)


class ApproveAndGateTest(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write_json("demo/storyboard.json", STORYBOARD)
        (self.demo / "scenes").mkdir()
        (self.demo / "scenes" / "01-intro.body.js").write_text("await intro({ title: 'T', durationMs: 1000 });\n")

    def test_approve_missing_file_fails(self):
        code, _, err = dv("approve", "survey", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)

    def test_approve_unknown_stage_fails(self):
        code, _, _ = dv("approve", "bogus", cwd=self.project)
        self.assertEqual(code, 2)

    def test_render_blocked_until_storyboard_approved(self):
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("G3 not passed", err)
        code, out, err = dv("approve", "storyboard", "--note", "ok", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.assertIn("G3", out)
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)

    def test_edit_after_approval_reblocks_until_reapproved(self):
        dv("approve", "storyboard", cwd=self.project)
        sb = self.read_json("demo/storyboard.json")
        sb["scenes"][0]["title"] = "Changed"
        self.write_json("demo/storyboard.json", sb)
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("changed since approval", err)
        dv("approve", "storyboard", cwd=self.project)
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)

    def test_machine_filled_fields_do_not_break_approval(self):
        """narrate writes holdMs/dwellMs/narration markup back; that must not invalidate G3."""
        dv("approve", "storyboard", cwd=self.project)
        sb = self.read_json("demo/storyboard.json")
        sb["scenes"][0]["dwellMs"] = 4200
        sb["scenes"][0]["steps"] = [{"action": "subtitle", "text": "x", "holdMs": 3000,
                                     "narration": "x[[slnc 300]]"}]
        self.write_json("demo/storyboard.json", sb)
        # the step list itself is new content, so this one must be stale...
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 1)
        # ...but once approved with the step, changing only holdMs/dwellMs/narration keeps it valid
        dv("approve", "storyboard", cwd=self.project)
        sb["scenes"][0]["dwellMs"] = 9000
        sb["scenes"][0]["steps"][0]["holdMs"] = 5000
        sb["scenes"][0]["steps"][0]["narration"] = "[[rate 120]]x"
        self.write_json("demo/storyboard.json", sb)
        code, _, err = dv("render", "--dry-run", cwd=self.project)
        self.assertEqual(code, 0, err)

    def test_final_stage_resolves_output_name(self):
        code, _, err = dv("approve", "final", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("output/t.mp4", err)
        (self.demo / "output").mkdir()
        (self.demo / "output" / "t.mp4").write_bytes(b"\x00")
        code, out, _ = dv("approve", "final", cwd=self.project)
        self.assertEqual(code, 0)
        self.assertIn("G4", out)


class StatusTest(ProjectCase):
    def test_status_reports_gates_and_next_step(self):
        code, _, err = dv("status", cwd=self.project)
        self.assertEqual(code, 0, err)
        self.write_json("demo/storyboard.json", STORYBOARD)
        (self.demo / "survey.json").write_text("{}")
        dv("approve", "survey", cwd=self.project)
        code, out, _ = dv("status", "--json", cwd=self.project)
        st = json.loads(out)
        by = {g["stage"]: g for g in st["gates"]}
        self.assertEqual(by["survey"]["status"], "approved")
        self.assertEqual(by["scenario"]["status"], "missing")
        self.assertIn("scenario", st["next"])
        (self.demo / "survey.json").write_text('{"changed": true}')
        code, out, _ = dv("status", "--json", cwd=self.project)
        st = json.loads(out)
        self.assertEqual(next(g for g in st["gates"] if g["stage"] == "survey")["status"], "stale")
        self.assertIn("approve survey", st["next"])

    def test_status_without_demo_fails(self):
        (self.demo).rmdir()
        code, _, err = dv("status", cwd=self.project)
        self.assertEqual(code, 1)
        self.assertIn("init", err)


if __name__ == "__main__":
    unittest.main()
