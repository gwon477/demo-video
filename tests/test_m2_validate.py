"""M2: one pass and one fail fixture per validate rule (DESIGN.md 6절 FR numbers)."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "demo-video" / "scripts"))
from lib import common, validate as V  # noqa: E402

THEME = common.load_theme()
SEL = {"list": "[data-testid=fail-list]", "row": "[data-testid=fail-row-1]", "stat": "[data-testid=stat-fail]",
       "log": "[data-testid=log-scroll]", "pw": "input[type=password]", "handle": "[data-testid=pointer-handle-3]",
       "card": "[data-testid=pointer-card-1]"}


def base_storyboard():
    return {
        "schemaVersion": 2,
        "meta": {"name": "t", "size": [1280, 720]},
        "intro": {"source": "html", "template": "default", "title": "T", "holdMs": 2500},
        "outro": {"source": "html", "template": "default", "title": "T", "cta": "다음", "holdMs": 3000},
        "scenes": [{
            "id": "01-a", "url": "/index.html", "page": "dashboard", "transitionIn": {"type": "fade", "ms": 400},
            "steps": [{"subtitle": {"text": "실패한 테스트를 먼저 봅니다", "hook": True},
                       "actions": [{"type": "click", "target": SEL["row"]}], "holdMs": 3000}],
            "dwellMs": 6000, "interactions": [],
        }],
    }


def base_survey(text_chars=1600):
    return {"schemaVersion": 2, "pages": [{"id": "dashboard", "route": "/index.html", "locators": dict(SEL),
                                           "density": {"textChars": text_chars, "interactive": 5}}]}


class RuleCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="dv-val-")
        self.demo = Path(self._tmp)
        self.write_survey(base_survey())

    def write_survey(self, survey):
        (self.demo / "survey.json").write_text(json.dumps(survey), encoding="utf-8")

    def run_v(self, sb, fix=False):
        f, est = V.validate(copy.deepcopy(sb) if not fix else sb, self.demo, THEME, fix=fix)
        return f

    def assert_rule_fails(self, sb, rule, where_part=None):
        f = self.run_v(sb)
        hits = [e for e in f.errors if e["rule"] == rule and (where_part is None or where_part in e["where"])]
        self.assertTrue(hits, f"expected {rule} error, got {[(e['rule'], e['msg']) for e in f.errors]}")

    def assert_ok(self, sb):
        f = self.run_v(sb)
        self.assertEqual(f.errors, [], [(e["rule"], e["where"], e["msg"]) for e in f.errors])


class SchemaTest(RuleCase):
    def test_base_passes(self):
        self.assert_ok(base_storyboard())

    def test_v1_storyboard_is_rejected_with_migration_hint(self):
        sb = {"name": "x", "scenes": [{"id": "a", "kind": "scene", "steps": []}]}
        f = self.run_v(sb)
        self.assertTrue(any(e["rule"] == "schema" and "schemaVersion 2" in e["msg"] for e in f.errors))

    def test_unknown_action_type_rejected(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["actions"].append({"type": "teleport", "target": SEL["row"]})
        self.assert_rule_fails(sb, "schema", "actions[1]")

    def test_all_action_types_accepted(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["actions"] = [
            {"type": "goto", "url": "/x"}, {"type": "click", "target": SEL["row"]}, {"type": "type", "target": SEL["row"], "value": "a"},
            {"type": "hover", "target": SEL["row"]}, {"type": "scroll", "target": SEL["log"], "toRatio": 1},
            {"type": "waitFor", "target": SEL["row"]}, {"type": "zoom", "target": SEL["list"]}, {"type": "zoomOut"},
            {"type": "highlight", "target": SEL["stat"]}, {"type": "chapter", "title": "c"},
            {"type": "drag", "source": SEL["handle"], "target": SEL["card"], "mode": "pointer"},
            {"type": "dropFile", "target": SEL["row"], "files": ["a.json"]}, {"type": "resize", "target": SEL["row"], "dx": 10},
            {"type": "slide", "target": SEL["row"], "value": 3}, {"type": "pan", "target": SEL["row"], "dx": 5},
            {"type": "wheelZoom", "target": SEL["row"]}, {"type": "key", "combo": "Meta+k"}, {"type": "dblclick", "target": SEL["row"]},
            {"type": "rightClick", "target": SEL["row"]}, {"type": "waitStream", "target": SEL["row"]}]
        sb["scenes"][0]["dwellMs"] = 9000
        sb["scenes"][0]["steps"][0]["holdMs"] = 1500
        f = self.run_v(sb)
        self.assertFalse([e for e in f.errors if e["rule"] == "schema"], f.errors)

    def test_drag_without_mode_rejected(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["actions"] = [{"type": "drag", "source": SEL["handle"], "target": SEL["card"]}]
        self.assert_rule_fails(sb, "schema")

    def test_duplicate_scene_id_rejected(self):
        sb = base_storyboard()
        sb["scenes"].append(copy.deepcopy(sb["scenes"][0]))
        self.assert_rule_fails(sb, "schema")


class SubtitleRulesTest(RuleCase):
    def test_fr011_newline_rejected(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["subtitle"]["text"] = "첫 줄\n둘째 줄"
        self.assert_rule_fails(sb, "FR-011")

    def test_fr012_32_hangul_pass_33_fail(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["subtitle"]["text"] = "가" * 32
        sb["scenes"][0]["steps"][0]["holdMs"] = 7000
        sb["scenes"][0]["dwellMs"] = 8000
        self.assert_ok(sb)
        sb["scenes"][0]["steps"][0]["subtitle"]["text"] = "가" * 33
        self.assert_rule_fails(sb, "FR-012")

    def test_fr012_latin_counts_half(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["subtitle"]["text"] = "a" * 60          # 30 weighted
        sb["scenes"][0]["steps"][0]["holdMs"] = 7000
        sb["scenes"][0]["dwellMs"] = 8000
        self.assert_ok(sb)
        sb["scenes"][0]["steps"][0]["subtitle"]["text"] = "a" * 66          # 33 weighted
        self.assert_rule_fails(sb, "FR-012")

    def test_fr013_hold_formula_and_fix(self):
        text = "실패한 테스트를 먼저 봅니다"      # 12 hangul + 3 spaces -> 13.5 weighted -> 2288
        self.assertEqual(V.hold_ms(text, THEME), round(13.5 * 125 + 600))
        self.assertEqual(V.hold_ms("가", THEME), THEME["subtitle"]["minMs"])
        self.assertEqual(V.hold_ms("가" * 60, THEME), THEME["subtitle"]["maxMs"])
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["holdMs"] = 1000
        self.assert_rule_fails(sb, "FR-013")
        del sb["scenes"][0]["steps"][0]["holdMs"]
        self.assert_rule_fails(sb, "FR-013")
        f = self.run_v(sb, fix=True)
        self.assertEqual(sb["scenes"][0]["steps"][0]["holdMs"], 2288)
        self.assertEqual(f.errors, [])

    def test_fr013_over_7s_rejected(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["holdMs"] = 7500
        sb["scenes"][0]["dwellMs"] = 8500
        self.assert_rule_fails(sb, "FR-013")

    def test_fr013_narration_extends_hold(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["narrationMs"] = 5000
        self.assert_rule_fails(sb, "FR-013")     # 3000 < 5000 + 400


class ZoomRulesTest(RuleCase):
    def zoom_sb(self, scale=1.5, with_out=True):
        sb = base_storyboard()
        acts = [{"type": "zoom", "target": SEL["list"], "scale": scale}]
        if with_out:
            acts.append({"type": "zoomOut"})
        sb["scenes"][0]["steps"][0]["actions"] = acts
        return sb

    def test_fr020_scale_range(self):
        self.assert_ok(self.zoom_sb(1.5))
        self.assert_rule_fails(self.zoom_sb(2.5), "FR-020")
        self.assert_rule_fails(self.zoom_sb(1.0), "FR-020")

    def test_fr021_zoom_out_required(self):
        self.assert_rule_fails(self.zoom_sb(with_out=False), "FR-021")

    def test_fr021_two_zooms_in_one_step(self):
        sb = self.zoom_sb()
        sb["scenes"][0]["steps"][0]["actions"].insert(1, {"type": "zoom", "target": SEL["stat"]})
        self.assert_rule_fails(sb, "FR-021")

    def test_fr022_no_zoom_on_sparse_page(self):
        self.write_survey(base_survey(text_chars=200))
        self.assert_rule_fails(self.zoom_sb(), "FR-022")
        self.write_survey(base_survey(text_chars=1600))
        self.assert_ok(self.zoom_sb())


class SecretsTest(RuleCase):
    def test_fr032_password_literal_rejected(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["actions"] = [{"type": "type", "target": SEL["pw"], "value": "hunter2", "secret": True}]
        self.assert_rule_fails(sb, "FR-032")
        sb["scenes"][0]["steps"][0]["actions"] = [{"type": "type", "target": SEL["pw"], "value": "ACCOUNTS.kim.password", "secret": True}]
        self.assert_ok(sb)

    def test_fr032_password_field_needs_secret_flag(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["actions"] = [{"type": "type", "target": SEL["pw"], "value": "ACCOUNTS.kim.password"}]
        self.assert_rule_fails(sb, "FR-032")


class StructureTest(RuleCase):
    def test_fr043_transition_type_and_length(self):
        sb = base_storyboard()
        sb["scenes"][0]["transitionIn"] = {"type": "pixelize", "ms": 400}
        self.assert_rule_fails(sb, "FR-043")
        sb["scenes"][0]["transitionIn"] = {"type": "fade", "ms": 900}
        self.assert_rule_fails(sb, "FR-043")
        sb["scenes"][0]["transitionIn"] = {"type": "cut"}
        self.assert_ok(sb)

    def test_fr044_hook_required(self):
        sb = base_storyboard()
        del sb["scenes"][0]["steps"][0]["subtitle"]["hook"]
        self.assert_rule_fails(sb, "FR-044", "steps[0]")

    def test_fr044_intro_and_outro_limits(self):
        sb = base_storyboard()
        sb["intro"]["holdMs"] = 4000
        self.assert_rule_fails(sb, "FR-044", "intro")
        sb = base_storyboard()
        del sb["outro"]["cta"]
        self.assert_rule_fails(sb, "FR-044", "outro")
        sb = base_storyboard()
        sb["outro"]["holdMs"] = 6000
        self.assert_rule_fails(sb, "FR-044", "outro")

    def test_fr045_default_warns_over_90s_without_target(self):
        sb = base_storyboard()
        for i in range(11):                       # 11 x 9s ~ 100s
            sc = copy.deepcopy(sb["scenes"][0])
            sc["id"] = f"{i + 2:02d}-x"
            sc["dwellMs"] = 9000
            sc["transitionIn"] = {"type": "cut"}
            sb["scenes"].append(sc)
        f = self.run_v(sb)
        self.assertFalse([e for e in f.errors if e["rule"] == "FR-045"], "length is never an error")
        self.assertTrue([w for w in f.warnings if w["rule"] == "FR-045"])

    def test_fr045_user_target_is_the_budget(self):
        sb = base_storyboard()
        for i in range(25):                       # ~230s
            sc = copy.deepcopy(sb["scenes"][0])
            sc["id"] = f"{i + 2:02d}-x"
            sc["dwellMs"] = 9000
            sc["transitionIn"] = {"type": "cut"}
            sb["scenes"].append(sc)
        (self.demo / "config.json").write_text(json.dumps({"video": {"targetSec": 240}}))
        f = self.run_v(sb)
        self.assertFalse([w for w in f.warnings if w["rule"] == "FR-045"], "within 15% of the 240s target")
        (self.demo / "config.json").write_text(json.dumps({"video": {"targetSec": 60}}))
        f = self.run_v(sb)
        self.assertTrue([w for w in f.warnings if "over the 60s target" in w["msg"]])
        sb["scenes"] = sb["scenes"][:3]
        (self.demo / "config.json").write_text(json.dumps({"video": {"targetSec": 120}}))
        f = self.run_v(sb)
        self.assertTrue([w for w in f.warnings if "under the 120s target" in w["msg"]])


class InteractionsTest(RuleCase):
    def inter(self, **over):
        it = {"kind": "hover", "target": SEL["row"], "evidence": {"source": "Tooltip.tsx", "screen": "호버 시 툴팁"},
              "decision": "skip", "reason": "보조 정보"}
        it.update(over)
        return it

    def test_fr060_both_evidence_required(self):
        sb = base_storyboard()
        sb["scenes"][0]["interactions"] = [self.inter(evidence={"source": "Tooltip.tsx"})]
        self.assert_rule_fails(sb, "FR-060")
        sb["scenes"][0]["interactions"] = [self.inter()]
        self.assert_ok(sb)

    def test_fr061_reason_required(self):
        sb = base_storyboard()
        sb["scenes"][0]["interactions"] = [self.inter(reason="")]
        self.assert_rule_fails(sb, "FR-061")

    def test_fr062_show_needs_matching_action(self):
        sb = base_storyboard()
        sb["scenes"][0]["interactions"] = [self.inter(decision="show")]
        self.assert_rule_fails(sb, "FR-062")
        sb["scenes"][0]["steps"][0]["actions"].append({"type": "hover", "target": SEL["row"]})
        self.assert_ok(sb)

    def test_fr062_key_matches_by_kind(self):
        sb = base_storyboard()
        sb["scenes"][0]["interactions"] = [self.inter(kind="key", target="#palette input", decision="show")]
        sb["scenes"][0]["steps"][0]["actions"].append({"type": "key", "combo": "Meta+k"})
        self.assert_ok(sb)

    def test_fr063_blocked_is_reported(self):
        sb = base_storyboard()
        sb["scenes"][0]["interactions"] = [self.inter(decision="blocked", reason="데이터 없음")]
        f = self.run_v(sb)
        self.assertEqual(f.errors, [])
        self.assertEqual(len(f.blocked), 1)

    def test_fr061_more_than_two_shows_warns(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["actions"] += [{"type": "hover", "target": SEL["row"]}, {"type": "scroll", "target": SEL["log"], "toRatio": 1},
                                                   {"type": "key", "combo": "Escape"}]
        sb["scenes"][0]["dwellMs"] = 6000
        sb["scenes"][0]["interactions"] = [self.inter(decision="show"), self.inter(kind="scroll", target=SEL["log"], decision="show"),
                                           self.inter(kind="key", target="", decision="show")]
        f = self.run_v(sb)
        self.assertTrue([w for w in f.warnings if w["rule"] == "FR-061"])


class LocatorsAndDwellTest(RuleCase):
    def test_unknown_locator_rejected(self):
        sb = base_storyboard()
        sb["scenes"][0]["steps"][0]["actions"] = [{"type": "click", "target": "[data-testid=invented]"}]
        self.assert_rule_fails(sb, "locators")

    def test_no_survey_only_warns(self):
        (self.demo / "survey.json").unlink()
        sb = base_storyboard()
        f = self.run_v(sb)
        self.assertFalse([e for e in f.errors if e["rule"] == "locators"])
        self.assertTrue([w for w in f.warnings if w["rule"] == "locators"])

    def test_dwell_fix_and_cap(self):
        sb = base_storyboard()
        del sb["scenes"][0]["dwellMs"]
        self.assert_rule_fails(sb, "dwell")
        f = self.run_v(sb, fix=True)
        # holds 3000 + 1 action * 600, floor from density 1600 chars: 2000+3556+1000 = 6556
        self.assertEqual(sb["scenes"][0]["dwellMs"], 6556)
        sb["scenes"][0]["steps"][0]["holdMs"] = 7000
        sb["scenes"][0]["steps"].append({"subtitle": {"text": "둘째"}, "holdMs": 3000, "actions": []})
        f = self.run_v(sb, fix=True)
        self.assertTrue([e for e in f.errors if e["rule"] == "dwell" and "exceeds" in e["msg"]])


if __name__ == "__main__":
    unittest.main()
