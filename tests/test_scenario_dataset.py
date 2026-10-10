import tempfile
import unittest
from pathlib import Path

from tools.scenario_dataset import build, information_state, read_json, snapshot, validate, write_json


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        build(self.root)

    def public(self, case="case_001"):
        return read_json(self.root / "cases" / case / "public.json")

    def test_all_fixtures_match_rubric(self):
        self.assertEqual(validate(self.root), {
            "cases": 3, "scene_groups": 3, "observations": 1980, "checkpoints": 360,
        })

    def test_briefings_match_distinct_scenarios(self):
        document = read_json(self.root / "briefings.json")
        self.assertTrue(document["author_preview"])
        self.assertEqual(len(document["cases"]), 3)
        self.assertEqual([b["case_id"] for b in document["cases"] if b["scenario_type"] == "load_test"], ["case_003"])
        for brief, count in zip(document["cases"], (12, 24, 36)):
            public = self.public(brief["case_id"])
            self.assertEqual(brief["object_ids"], public["object_ids"])
            self.assertEqual(brief["object_count"], count)
            self.assertEqual(brief["duration_ms"], 180000)
            self.assertEqual(brief["sample_interval_ms"], 10000)
            for field in ("name", "summary", "objective", "composition", "count_basis"):
                self.assertEqual(set(brief[field]), {"en", "ko"})
            self.assertTrue(all(set(step["text"]) == {"en", "ko"} for step in brief["timeline"]))

    def test_initial_receipts_are_staggered_and_no_unknown_ids_or_context_leak(self):
        for case in ("case_001", "case_002", "case_003"):
            public = self.public(case)
            empty = snapshot(public, 9999)
            self.assertEqual(empty["object_ids"], [])
            self.assertEqual(empty["contexts"], [])
            first = snapshot(public, 10000)
            self.assertGreater(len(first["object_ids"]), 0)
            self.assertLess(len(first["object_ids"]), len(public["object_ids"]))
            self.assertEqual(set(first["object_ids"]), {r["object_id"] for r in first["observations"]})
            self.assertEqual(information_state(first, "object_11"), "missing")
            self.assertEqual(information_state(snapshot(public, 14000), "object_11"), "consistent")

    def test_delayed_older_report_does_not_replace_newer_observation(self):
        public = self.public()
        delayed = next(r for r in public["observations"] if r["object_id"] == "object_11"
                       and r["source_id"] == "channel_b" and r["observed_at_ms"] == 40000)
        self.assertEqual(delayed["available_at_ms"], 55000)
        self.assertEqual(information_state(snapshot(public, 40000), "object_11"), "not_comparable")
        self.assertEqual(information_state(snapshot(public, 55000), "object_11"), "consistent")

    def test_outage_and_conflicting_labels_recover(self):
        for case in ("case_002", "case_003"):
            payload = snapshot(self.public(case), 130000)
            self.assertTrue(all(information_state(payload, obj) == "consistent" for obj in payload["object_ids"]))
        payload = snapshot(self.public("case_002"), 90000)
        states = [information_state(payload, obj) for obj in payload["object_ids"]]
        self.assertEqual(states.count("contradictory"), 6)
        self.assertEqual(states.count("consistent"), 18)

    def test_regeneration_is_byte_identical(self):
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*.json")}
        build(self.root)
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*.json")}
        self.assertEqual(before, after)

    def test_future_events_and_unpublished_context_are_hidden(self):
        payload = snapshot(self.public("case_003"), 59_999)
        self.assertTrue(all(row["observed_at_ms"] < 60_000 for row in payload["observations"]))
        self.assertTrue(all(row["status"] == "online" for row in payload["source_health"]))
        self.assertEqual([row["id"] for row in payload["contexts"]], ["context_001"])
        self.assertEqual(len(snapshot(self.public(), 90_000)["contexts"]), 2)

    def test_observation_waits_for_arrival(self):
        public = self.public()
        public["observations"][0]["available_at_ms"] = 40_000
        self.assertNotIn("obs_0001", [row["id"] for row in snapshot(public, 30_000)["observations"]])
        self.assertIn("obs_0001", [row["id"] for row in snapshot(public, 40_000)["observations"]])

    def test_export_uses_allowlist(self):
        public = self.public()
        public["expected_state"] = "secret"
        public["observations"][0]["ground_truth"] = "secret"
        payload = snapshot(public, 10000)
        self.assertNotIn("expected_state", payload)
        self.assertNotIn("ground_truth", payload["observations"][0])

    def test_missing_channel_keeps_last_observation_without_confirmation(self):
        payload = snapshot(self.public("case_003"), 90_000)
        obj = payload["object_ids"][0]
        self.assertEqual(information_state(payload, obj), "missing")
        self.assertEqual(max(row["observed_at_ms"] for row in payload["observations"]
                             if row["source_id"] == "channel_b"), 50_000)

    def test_each_branch_has_independently_expected_state(self):
        expected = {"case_001": "consistent", "case_002": "contradictory", "case_003": "missing"}
        for case, state in expected.items():
            payload = snapshot(self.public(case), 60_000)
            self.assertEqual(information_state(payload, "object_11"), state)
            self.assertEqual(information_state(snapshot(self.public(case), 59_999), "object_11"), "consistent")

    def test_different_sample_times_are_not_compared(self):
        payload = snapshot(self.public(), 30_000)
        payload["observations"] = [row for row in payload["observations"]
                                   if not (row["source_id"] == "channel_b" and row["observed_at_ms"] == 30_000)]
        self.assertEqual(information_state(payload, "object_11"), "not_comparable")

    def test_stale_health_and_observations_cannot_confirm(self):
        payload = snapshot(self.public(), 14000)
        payload["at_ms"] = 55_001
        self.assertEqual(information_state(payload, "object_11"), "missing")

    def test_demo_cannot_claim_holdout_validation(self):
        manifest = read_json(self.root / "manifest.json")
        manifest["cases"][0]["split"] = "holdout"
        write_json(self.root / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "not a holdout"):
            validate(self.root)

    def test_duplicate_evidence_is_rejected(self):
        public = self.public()
        public["observations"][1]["id"] = public["observations"][0]["id"]
        write_json(self.root / "cases" / "case_001" / "public.json", public)
        with self.assertRaisesRegex(ValueError, "Duplicate evidence"):
            validate(self.root)

    def test_invalid_time_is_rejected(self):
        for at_ms in (-1, 180_001, 1.5, True):
            with self.assertRaises(ValueError):
                snapshot(self.public(), at_ms)


if __name__ == "__main__":
    unittest.main()
