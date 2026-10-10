import json
import unittest

from tools.scenario_dataset import ROOT, read_json, snapshot as observation_snapshot
from tools.sensor_fleet import snapshot


class SensorFleetTests(unittest.TestCase):
    def test_counts_are_240_distinct_logical_endpoints_in_four_groups(self):
        state = snapshot("case_001", 1000)
        self.assertEqual(state["total"], 240)
        self.assertEqual(state["counts"], {"online": 240, "offline": 0, "stale": 0, "waiting": 0})
        self.assertEqual(len({row["id"] for row in state["sensors"]}), 240)
        self.assertEqual({g["id"] for g in state["groups"]},
                         {"personnel_phone", "facility_sensor", "civilian_phone", "fixed_phone"})
        self.assertTrue(all(group["total"] == 60 for group in state["groups"]))
        self.assertEqual(sum(sum(group["counts"].values()) for group in state["groups"]), 240)

    def test_initial_heartbeat_waits_for_receipt_and_no_future_events_leak(self):
        before = snapshot("case_003", 999)
        self.assertEqual(before["counts"]["waiting"], 240)
        self.assertTrue(all(row["evidence_id"] is None and row["last_seen_ms"] is None
                            for row in before["sensors"]))
        after = snapshot("case_003", 1000)
        self.assertEqual(after["counts"]["online"], 240)
        self.assertTrue(all(row["observed_at_ms"] == 0 and row["available_at_ms"] == 1000
                            for row in after["sensors"]))
        self.assertNotIn("interruptions", after)
        self.assertEqual(snapshot("case_003", 60999)["counts"]["offline"], 0)
        self.assertEqual(snapshot("case_003", 61000)["counts"]["offline"], 60)

    def test_silence_becomes_stale_without_claiming_cause(self):
        self.assertEqual(snapshot("case_003", 70000)["counts"]["stale"], 0)
        state = snapshot("case_003", 70001)
        self.assertEqual(state["counts"], {"online": 120, "offline": 60, "stale": 60, "waiting": 0})
        stale = next(row for row in state["sensors"] if row["status"] == "stale")
        self.assertEqual(stale["observed_at_ms"], 50000)
        self.assertEqual(stale["last_seen_ms"], 51000)
        self.assertTrue(all(row["cause"] == "unknown" for row in state["sensors"]
                            if row["status"] in ("offline", "stale")))

    def test_recovery_is_received_and_rewind_is_deterministic(self):
        loss = snapshot("case_003", 90000)
        self.assertEqual(snapshot("case_003", 130999)["counts"]["online"], 120)
        recovered = snapshot("case_003", 131000)
        self.assertEqual(recovered["counts"]["online"], 240)
        self.assertTrue(all(row["last_seen_ms"] == 131000 for row in recovered["sensors"]))
        self.assertEqual(snapshot("case_003", 90000), loss)
        for case in ("case_001", "case_002"):
            self.assertEqual(snapshot(case, 90000)["counts"]["online"], 240)

    def test_health_does_not_create_tracks_or_expose_world_data(self):
        health = snapshot("case_003", 1000)
        self.assertTrue(health["health_only"])
        serialized = json.dumps(health)
        for forbidden in ("object_id", "position", "keyframes", "marker_label", "channel_a", "channel_b"):
            self.assertNotIn(forbidden, serialized)
        observations = observation_snapshot(read_json(ROOT / "cases/case_003/public.json"), 1000)
        self.assertEqual(observations["object_ids"], [])
        self.assertEqual(observations["observations"], [])

    def test_payload_is_latest_only_and_time_valid(self):
        for at_ms in (0, 1000, 59999, 61000, 70001, 131000, 180000):
            state = snapshot("case_003", at_ms)
            self.assertEqual(len(state["sensors"]), 240)
            self.assertEqual(sum(state["counts"].values()), 240)
            self.assertTrue(all(row["observed_at_ms"] <= row["available_at_ms"] <= at_ms
                                for row in state["sensors"] if row["available_at_ms"] is not None))
        for at_ms in (-1, 180001, 1.5, True):
            with self.assertRaises(ValueError):
                snapshot("case_003", at_ms)
        with self.assertRaises(ValueError):
            snapshot("case_999", 1000)


if __name__ == "__main__":
    unittest.main()
