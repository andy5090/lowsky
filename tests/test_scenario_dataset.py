import tempfile
import unittest
from pathlib import Path

from tools.scenario_dataset import authored_time, build, information_state, read_json, snapshot, validate, write_json


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        build(self.root)

    def public(self, case="case_001"):
        return read_json(self.root / "cases" / case / "public.json")

    def at(self, old_ms, case="case_001"):
        return authored_time({"case_001": "consistent", "case_002": "contradictory", "case_003": "missing"}[case], old_ms)

    def test_all_fixtures_match_rubric(self):
        self.assertEqual(validate(self.root), {
            "cases": 3, "scene_groups": 3, "observations": 10224, "checkpoints": 1920,
        })

    def test_briefings_match_distinct_scenarios(self):
        document = read_json(self.root / "briefings.json")
        self.assertTrue(document["author_preview"])
        self.assertEqual(len(document["cases"]), 3)
        self.assertEqual([b["case_id"] for b in document["cases"] if b["scenario_type"] == "load_test"], ["case_003"])
        for brief, count in zip(document["cases"], (48, 96, 240)):
            public = self.public(brief["case_id"])
            world = read_json(self.root / "cases" / brief["case_id"] / "world.json")
            rubric = read_json(self.root / "evaluation" / f"{brief['case_id']}.json")
            self.assertEqual(brief["object_ids"], public["object_ids"])
            self.assertEqual(brief["object_count"], count)
            self.assertEqual([obj["object_id"] for obj in world["objects"]], public["object_ids"])
            self.assertEqual(len(world["objects"]), count)
            self.assertEqual(len(rubric["checkpoints"]), count * 5)
            self.assertEqual(brief["duration_ms"], self.at(180000, brief["case_id"]))
            self.assertEqual(brief["sample_interval_ms"], 10000 if brief["case_id"] == "case_003" else 30000)
            for field in ("name", "summary", "objective", "composition", "count_basis"):
                self.assertEqual(set(brief[field]), {"en", "ko"})
            self.assertTrue(all(set(step["text"]) == {"en", "ko"} for step in brief["timeline"]))

    def test_load_case_is_bounded_and_all_tracks_require_received_reports(self):
        public = self.public("case_003")
        world = read_json(self.root / "cases/case_003/world.json")
        self.assertEqual(len(world["objects"]), 240)
        for obj in world["objects"]:
            for row in obj["keyframes"]:
                x, y, z = row["position"]
                self.assertLessEqual(abs(x), 830)
                self.assertTrue(80 <= y <= 128)
                self.assertTrue(-2300 <= z <= 1900)
        self.assertEqual(snapshot(public, 9999)["object_ids"], [])
        self.assertEqual(len(snapshot(public, 60000)["object_ids"]), 240)
        self.assertEqual(len(snapshot(public, 180000)["object_ids"]), 240)

    def test_initial_receipts_are_staggered_and_no_unknown_ids_or_context_leak(self):
        for case in ("case_001", "case_002", "case_003"):
            public = self.public(case)
            empty = snapshot(public, self.at(10000, case) - 1)
            self.assertEqual(empty["object_ids"], [])
            self.assertEqual(empty["contexts"], [])
            first = snapshot(public, self.at(10000, case))
            self.assertGreater(len(first["object_ids"]), 0)
            self.assertLess(len(first["object_ids"]), len(public["object_ids"]))
            self.assertEqual(set(first["object_ids"]), {r["object_id"] for r in first["observations"]})
            self.assertEqual(information_state(first, "object_11"), "missing")
            self.assertEqual(information_state(snapshot(public, self.at(14000, case)), "object_11"), "consistent")

    def test_delayed_older_report_does_not_replace_newer_observation(self):
        public = self.public()
        delayed = next(r for r in public["observations"] if r["object_id"] == "object_11"
                       and r["source_id"] == "channel_b" and r["observed_at_ms"] == self.at(40000))
        self.assertEqual(delayed["available_at_ms"], self.at(55000))
        self.assertEqual(information_state(snapshot(public, self.at(40000)), "object_11"), "not_comparable")
        self.assertEqual(information_state(snapshot(public, self.at(55000)), "object_11"), "consistent")

    def test_outage_and_conflicting_labels_recover(self):
        for case in ("case_002", "case_003"):
            payload = snapshot(self.public(case), self.at(130000, case))
            self.assertTrue(all(information_state(payload, obj) == "consistent" for obj in payload["object_ids"]))
        payload = snapshot(self.public("case_002"), self.at(90000, "case_002"))
        states = [information_state(payload, obj) for obj in payload["object_ids"]]
        self.assertEqual(states.count("contradictory"), 24)
        self.assertEqual(states.count("consistent"), 72)

    def test_paced_cases_have_real_indirect_only_time_and_consistent_world_clock(self):
        for case in ("case_001", "case_002"):
            public = self.public(case)
            self.assertEqual(public["duration_ms"], 780000)
            self.assertEqual(public["training_timing"],
                             {"paced": True, "early_review_ms": 120000, "received_review_ms": 90000})
            self.assertEqual(public["training_schedule"]["first_direct_observation_ms"], 270000)
            self.assertEqual(snapshot(public, 269999)["object_ids"], [])
            self.assertTrue(snapshot(public, 270000)["object_ids"])
            self.assertNotIn("training_schedule", snapshot(public, 0))
            world = read_json(self.root / "cases" / case / "world.json")
            frames = {obj["object_id"]: {row["at_ms"]: row["position"] for row in obj["keyframes"]}
                      for obj in world["objects"]}
            self.assertNotEqual(frames["object_11"][0], frames["object_11"][240000])
            self.assertEqual(frames["object_11"][0][2], -18000)
            self.assertEqual(frames["object_11"][270000][2], -2200)
            self.assertEqual(frames["object_11"][780000][2], 1900)
            self.assertGreaterEqual(min(frame["position"][2] for obj in world["objects"] for frame in obj["keyframes"]), -19200)
            for row in public["observations"]:
                self.assertEqual(row["position"], frames[row["object_id"]][row["observed_at_ms"]])
            self.assertEqual(len(snapshot(public, 780000)["object_ids"]), len(public["object_ids"]))

    def test_seeded_paced_receipts_are_repeatable_and_do_not_shorten_early_period(self):
        from tools.simulation_test import generate
        from tools.build_early_warning import PATH
        import json
        early = json.loads(PATH.read_text())
        fleet = read_json(Path(__file__).resolve().parents[1] / "data/sensor_fleet_demo.json")
        for case in ("case_001", "case_002"):
            profile = {**early, **early["case_overrides"][case]}
            profile.pop("case_overrides")
            original = self.public(case)
            first = generate(case, 42, original, profile, fleet)
            self.assertEqual(first, generate(case, 42, original, profile, fleet))
            self.assertEqual(snapshot(first[0], 269999)["object_ids"], [])
            self.assertEqual(first[0]["duration_ms"], 780000)
            authored = {row["id"]: row for row in original["observations"]}
            for row in first[0]["observations"]:
                self.assertEqual(row["position"], authored[row["id"]]["position"])
                self.assertEqual(row["observed_at_ms"], authored[row["id"]]["observed_at_ms"])
                self.assertGreaterEqual(row["available_at_ms"], row["observed_at_ms"])

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
        self.assertEqual(len(snapshot(self.public(), self.at(90_000))["contexts"]), 2)

    def test_observation_waits_for_arrival(self):
        public = self.public()
        public["observations"][0]["available_at_ms"] = self.at(40_000)
        self.assertNotIn("obs_0001", [row["id"] for row in snapshot(public, self.at(30_000))["observations"]])
        self.assertIn("obs_0001", [row["id"] for row in snapshot(public, self.at(40_000))["observations"]])

    def test_export_uses_allowlist(self):
        public = self.public()
        public["expected_state"] = "secret"
        public["observations"][0]["ground_truth"] = "secret"
        payload = snapshot(public, self.at(10000))
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
            payload = snapshot(self.public(case), self.at(60_000, case))
            self.assertEqual(information_state(payload, "object_11"), state)
            self.assertEqual(information_state(snapshot(self.public(case), self.at(60_000, case) - 1), "object_11"), "consistent")

    def test_different_sample_times_are_not_compared(self):
        payload = snapshot(self.public(), self.at(30_000))
        payload["observations"] = [row for row in payload["observations"]
                                   if not (row["source_id"] == "channel_b" and row["observed_at_ms"] == self.at(30_000))]
        self.assertEqual(information_state(payload, "object_11"), "not_comparable")

    def test_stale_health_and_observations_cannot_confirm(self):
        payload = snapshot(self.public(), self.at(14000))
        payload["at_ms"] = self.at(55_001)
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
        for at_ms in (-1, 780_001, 1.5, True):
            with self.assertRaises(ValueError):
                snapshot(self.public(), at_ms)


if __name__ == "__main__":
    unittest.main()
