"""Shared test helpers: run dv.py as a subprocess against a temp project."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DV = REPO / "skills" / "demo-video" / "scripts" / "dv.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def dv(*args, cwd, env=None):
    """Run dv.py with args in cwd; returns (returncode, stdout, stderr)."""
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    r = subprocess.run([sys.executable, str(DV), *map(str, args)], cwd=str(cwd),
                       capture_output=True, text=True, env=e)
    return r.returncode, r.stdout, r.stderr


class ProjectCase(unittest.TestCase):
    """A temp project folder with an empty demo/ per test."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="dv-test-")
        self.project = Path(self._tmp)
        self.demo = self.project / "demo"
        self.demo.mkdir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_json(self, rel, data):
        p = self.project / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return p

    def read_json(self, rel):
        return json.loads((self.project / rel).read_text(encoding="utf-8"))

    def copy_fixture(self, name):
        shutil.copytree(FIXTURES / name, self.demo, dirs_exist_ok=True)
