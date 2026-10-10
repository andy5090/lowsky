import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import monitor_server
from tools.scenario_dataset import build, write_json


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class SimulationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        build(self.root)
        self.clock = FakeClock()
        self.sim = monitor_server.Simulation(self.root, clock=self.clock)

    def select(self, case_id, at_ms=0):
        self.sim.control({"action": "case", "case_id": case_id})
        return self.sim.control({"action": "seek", "at_ms": at_ms})


class SimulationTests(SimulationFixture):
    def test_clock_play_pause_and_speed_preserve_elapsed_time(self):
        self.clock.advance(7)
        self.assertEqual(self.sim.clock_state()["at_ms"], 0)
        self.sim.control({"action": "play"})
        self.clock.advance(3)
        self.assertEqual(self.sim.clock_state()["at_ms"], 3000)
        changed = self.sim.control({"action": "speed", "speed": 2})
        self.assertEqual(changed["at_ms"], 3000)
        self.clock.advance(5)
        paused = self.sim.control({"action": "pause"})
        self.assertEqual(paused["at_ms"], 13000)
        self.assertFalse(paused["playing"])
        self.clock.advance(10)
        self.assertEqual(self.sim.clock_state()["at_ms"], 13000)
        self.sim.control({"action": "play"})
        self.clock.advance(1)
        self.assertEqual(self.sim.clock_state()["at_ms"], 15000)

    def test_end_clamps_and_play_starts_a_new_run(self):
        self.sim.control({"action": "seek", "at_ms": 179000})
        self.sim.control({"action": "play"})
        run_id = self.sim.clock_state()["run_id"]
        self.clock.advance(10)
        ended = self.sim.clock_state()
        self.assertEqual(ended["at_ms"], 180000)
        self.assertFalse(ended["playing"])
        restarted = self.sim.control({"action": "play"})
        self.assertEqual(restarted["at_ms"], 0)
        self.assertTrue(restarted["playing"])
        self.assertNotEqual(restarted["run_id"], run_id)

    def test_seek_reanchors_playing_clock_and_changes_run(self):
        self.sim.control({"action": "play"})
        self.clock.advance(20)
        run_id = self.sim.clock_state()["run_id"]
        state = self.sim.control({"action": "seek", "at_ms": 5000})
        self.assertEqual(state["at_ms"], 5000)
        self.assertTrue(state["playing"])
        self.assertNotEqual(state["run_id"], run_id)
        self.clock.advance(2)
        self.assertEqual(self.sim.clock_state()["at_ms"], 7000)

    def test_invalid_controls_do_not_change_clock_revision_or_run(self):
        invalid = [
            {"action": "seek", "at_ms": value}
            for value in (-1, 180001, True, 1.5, "3000", None)
        ] + [
            {"action": "speed", "speed": value}
            for value in (0, 3, True, "2", None, float("nan"))
        ] + [{"action": "case", "case_id": "unknown"}, {"action": "launch"}, {}]
        for command in invalid:
            with self.subTest(command=command):
                before = self.sim.clock_state()
                with self.assertRaises(ValueError):
                    self.sim.control(command)
                self.assertEqual(self.sim.clock_state(), before)

    def test_successful_controls_increment_revision_only_once(self):
        self.assertEqual(self.sim.clock_state()["revision"], 0)
        for revision, command in enumerate((
            {"action": "play"}, {"action": "pause"},
            {"action": "speed", "speed": 4},
            {"action": "seek", "at_ms": 500}, {"action": "reset"},
        ), 1):
            self.assertEqual(self.sim.control(command)["revision"], revision)
            self.assertEqual(self.sim.state()["revision"], revision)

    def test_snapshot_excludes_future_observations_health_and_context(self):
        state = self.select("case_003", 59999)
        self.assertTrue(state["synthetic"])
        self.assertEqual(state["coordinate_system"], "fictional_local_meters")
        self.assertEqual([row["id"] for row in state["contexts"]], ["context_001"])
        self.assertTrue(all(source["status"] == "online" for source in state["sources"]))
        for track in state["tracks"]:
            self.assertEqual(track["quality"], "consistent")
            for row in track["records"] + track["history"]:
                self.assertLessEqual(row["observed_at_ms"], 59999)
                self.assertLessEqual(row["available_at_ms"], 59999)
        later = self.sim.control({"action": "seek", "at_ms": 90000})
        self.assertEqual(len(later["contexts"]), 2)

    def test_delayed_arrival_never_leaks_into_track_or_history(self):
        public = self.sim.public[self.sim.case_id]
        for row in public["observations"]:
            if row["observed_at_ms"] >= 30000:
                row["available_at_ms"] = max(row["available_at_ms"], 40000)
        before = self.sim.control({"action": "seek", "at_ms": 39999})
        self.assertTrue(all(track["observed_at_ms"] == 20000 for track in before["tracks"]))
        self.assertTrue(all(row["observed_at_ms"] <= 20000
                            for track in before["tracks"] for row in track["history"]))
        after = self.sim.control({"action": "seek", "at_ms": 40000})
        self.assertTrue(all(track["observed_at_ms"] >= 30000 for track in after["tracks"]))

    def test_world_truth_and_author_annotations_are_not_exported(self):
        public = self.sim.public[self.sim.case_id]
        public["world_truth"] = "private-world-canary"
        public["observations"][0]["ground_truth"] = "private-record-canary"
        public["source_health"][0]["expected_state"] = "private-health-canary"
        public["contexts"][0]["answer"] = "private-context-canary"
        for world in (self.root / "cases").glob("*/world.json"):
            world.write_text("not valid JSON: must never be read", encoding="utf-8")
        # A new instance must also initialize and serve without reading world.json.
        monitor_server.Simulation(self.root, clock=self.clock).state()
        encoded = json.dumps(self.sim.state())
        for forbidden in ("world_truth", "ground_truth", "expected_state", "answer", "private-"):
            self.assertNotIn(forbidden, encoded)

    def test_position_is_last_observation_not_interpolated_world_position(self):
        public = self.sim.public[self.sim.case_id]
        for row in public["observations"]:
            if row["object_id"] == "object_11":
                row["position"] = [100, 10, 200] if row["observed_at_ms"] == 10000 else [300, 10, 400]
        state = self.sim.control({"action": "seek", "at_ms": 15000})
        track = next(track for track in state["tracks"] if track["object_id"] == "object_11")
        self.assertEqual(track["position"], [100, 10, 200])
        self.assertEqual(track["observed_at_ms"], 10000)
        self.assertFalse(track["last_known"])

    def test_missing_channel_preserves_its_evidence_but_uses_online_position(self):
        state = self.select("case_003", 90000)
        self.assertEqual({s["source_id"]: s["status"] for s in state["sources"]},
                         {"channel_a": "online", "channel_b": "offline"})
        for track in state["tracks"]:
            self.assertEqual(track["quality"], "missing")
            self.assertEqual(track["position_source"], "channel_a")
            self.assertEqual(track["observed_at_ms"], 90000)
            self.assertFalse(track["last_known"])
            missing_record = next((r for r in track["records"] if r["source_id"] == "channel_b"), None)
            if (int(track["object_id"].split("_")[1]) - 11) % 6 == 5:
                self.assertIsNone(missing_record)  # First seen after channel B went offline.
            else:
                self.assertEqual(missing_record["observed_at_ms"], 50000)
        self.assertIn("channel_b:offline", {a["id"] for a in state["alerts"]})

    def test_stale_sources_leave_last_known_position_instead_of_prediction(self):
        public = self.sim.public[self.sim.case_id]
        public["observations"] = [r for r in public["observations"] if r["observed_at_ms"] == 10000]
        public["source_health"] = [r for r in public["source_health"] if r["observed_at_ms"] == 10000]
        for row in public["observations"]:
            row["position"] = [100, 10, 200]
        fresh = self.sim.control({"action": "seek", "at_ms": 55000})
        self.assertFalse(fresh["tracks"][0]["last_known"])
        stale = self.sim.control({"action": "seek", "at_ms": 55001})
        self.assertTrue(all(s["status"] == "stale" for s in stale["sources"]))
        for track in stale["tracks"]:
            self.assertTrue(track["last_known"])
            self.assertEqual(track["observed_at_ms"], 10000)
            self.assertEqual(track["quality"], "missing")
        self.assertEqual(stale["tracks"][0]["position"], [100, 10, 200])
        self.assertIn("object_11:stale", {a["id"] for a in stale["alerts"]})

    def test_absent_observations_return_no_position_or_invented_history(self):
        public = self.sim.public[self.sim.case_id]
        public["observations"] = []
        public["source_health"] = []
        state = self.sim.state()
        self.assertEqual(state["tracks"], [])
        self.assertFalse(any("object_id" in alert for alert in state["alerts"]))
        self.assertTrue(all(s["status"] == "unknown" for s in state["sources"]))

    def test_unreceived_first_detection_does_not_reveal_an_object(self):
        public = self.sim.public[self.sim.case_id]
        # One candidate arrives late; other world objects have never been observed.
        row = dict(public["observations"][0], observed_at_ms=10000, available_at_ms=15000)
        public["observations"] = [row]
        before = self.sim.control({"action": "seek", "at_ms": 14999})
        self.assertEqual(before["tracks"], [])
        self.assertFalse(any("object_id" in a for a in before["alerts"]))
        after = self.sim.control({"action": "seek", "at_ms": 15000})
        self.assertEqual([t["object_id"] for t in after["tracks"]], [row["object_id"]])
        self.assertEqual(after["tracks"][0]["observed_at_ms"], 10000)
        rewind = self.sim.control({"action": "seek", "at_ms": 0})
        self.assertEqual(rewind["tracks"], [])

    def test_negative_detection_never_reveals_author_object(self):
        public = self.sim.public[self.sim.case_id]
        public['observations'] = [dict(public['observations'][0], detected=False)]
        state = self.sim.control({'action': 'seek', 'at_ms': 60000})
        self.assertEqual(state['tracks'], [])
        self.assertFalse(any('object_id' in alert for alert in state['alerts']))

    def test_truth_requires_explicit_opt_in_and_never_becomes_evidence(self):
        normal = self.sim.state()
        truth = self.sim.state(show_positions=True)
        self.assertEqual(normal['tracks'], [])
        self.assertNotIn('simulation_positions', normal)
        self.assertEqual(len(truth['simulation_positions']), 12)
        positions = truth.pop('simulation_positions')
        self.assertEqual(truth, normal)
        self.assertEqual(set(positions[0]), {'object_id', 'position'})
        self.sim.control({'action': 'seek', 'at_ms': 5000})
        later = self.sim.state(show_positions=True)
        self.assertNotEqual(later['simulation_positions'][0]['position'], positions[0]['position'])
        self.assertEqual(later['tracks'], [])
        self.assertAlmostEqual(later['simulation_positions'][0]['position'][2], -1900 + 3800 / 36)
        self.sim.control({'action': 'case', 'case_id': 'case_003'})
        self.assertEqual(len(self.sim.state(show_positions=True)['simulation_positions']), 36)
        self.assertNotIn('simulation_positions', self.sim.state())

    def test_different_observation_times_raise_comparison_alert_with_evidence(self):
        public = self.sim.public[self.sim.case_id]
        public["observations"] = [r for r in public["observations"]
                                  if not (r["source_id"] == "channel_b" and r["observed_at_ms"] == 30000)]
        state = self.sim.control({"action": "seek", "at_ms": 30000})
        track = next(t for t in state["tracks"] if t["object_id"] == "object_11")
        self.assertEqual(track["quality"], "not_comparable")
        alert = next(a for a in state["alerts"] if a["id"] == "object_11:not_comparable")
        self.assertEqual(set(alert["evidence_ids"]), {r["id"] for r in track["records"]})
        self.assertFalse(alert["acknowledged"])

    def test_ack_requires_current_alert_and_matching_run(self):
        state = self.select("case_002", 60000)
        alert_id = "object_11:contradictory"
        self.assertIn(alert_id, {a["id"] for a in state["alerts"]})
        for invalid in ({"run_id": "old", "alert_id": alert_id},
                        {"run_id": state["run_id"], "alert_id": "unknown"}):
            with self.assertRaises(ValueError):
                self.sim.control({"action": "ack", **invalid})
        acknowledged = self.sim.control({"action": "ack", "run_id": state["run_id"], "alert_id": alert_id})
        self.assertTrue(next(a for a in acknowledged["alerts"] if a["id"] == alert_id)["acknowledged"])
        self.assertEqual(acknowledged["run_id"], state["run_id"])

    def test_seek_reset_and_case_change_clear_acknowledgements(self):
        for command in ({"action": "seek", "at_ms": 60000},
                        {"action": "reset"}, {"action": "case", "case_id": "case_003"}):
            with self.subTest(command=command):
                state = self.select("case_002", 60000)
                self.sim.control({"action": "ack", "run_id": state["run_id"],
                                  "alert_id": "object_11:contradictory"})
                after = self.sim.control(command)
                self.assertNotEqual(after["run_id"], state["run_id"])
                self.assertFalse(any(a["acknowledged"] for a in after["alerts"]))
                if command["action"] in ("reset", "case"):
                    self.assertEqual(after["at_ms"], 0)
                    self.assertFalse(after["playing"])
                if command["action"] == "case":
                    self.assertEqual(after["case_id"], "case_003")
                with self.assertRaisesRegex(ValueError, "Stale run"):
                    self.sim.control({"action": "ack", "run_id": state["run_id"],
                                      "alert_id": "object_11:contradictory"})


class HTTPTests(SimulationFixture):
    def setUp(self):
        super().setUp()
        self.project = self.root / "project"
        (self.project / "monitor").mkdir(parents=True)
        self.assets = {"/": ("index.html", b"<!doctype html><title>test monitor</title>"),
                       "/app.js": ("app.js", b"export const synthetic = true;"),
                       "/styles.css": ("styles.css", b"body { color: navy; }")}
        for name in ('manifest.webmanifest', 'notifications.mjs', 'sw.js', 'pwa-icon.svg'):
            self.assets['/' + name] = (name, (monitor_server.PROJECT / 'monitor' / name).read_bytes())
        for filename, content in self.assets.values():
            (self.project / "monitor" / filename).write_bytes(content)
        (self.project / "monitor" / "private.txt").write_text("private file", encoding="utf-8")
        write_json(self.project / "data" / "site_layout.json", {"synthetic": True})
        write_json(self.project / "monitor" / "map_config.json", {"reference_only": True})
        write_json(self.project / "data" / "radar_display.json", {"synthetic": True, "stations": []})
        write_json(self.project / "data/references/ukraine_observation_lessons.json", {"sources": []})
        project_patch = patch.object(monitor_server, "PROJECT", self.project)
        project_patch.start()
        self.addCleanup(project_patch.stop)
        logging_patch = patch.object(monitor_server.Handler, "log_message")
        logging_patch.start()
        self.addCleanup(logging_patch.stop)
        self.server = monitor_server.make_server(0, simulation=self.sim)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post(self, command, headers=None):
        return self.request("POST", "/api/control", json.dumps(command),
                            {"Content-Type": "application/json", "Origin": self.origin, **(headers or {})})

    def test_monitor_cannot_fetch_author_motion(self):
        for path in ("/api/preview", "/motion.mjs"):
            status, _, _ = self.request("GET", path)
            self.assertEqual(status, 404)

    def test_truth_query_is_explicit_separate_and_not_cached(self):
        for query in ('', '?show_positions=0', '?show_positions=true'):
            status, _, raw = self.request('GET', '/api/state' + query)
            self.assertEqual(status, 200)
            self.assertNotIn('simulation_positions', json.loads(raw))
        status, headers, raw = self.request('GET', '/api/state?show_positions=1')
        state = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(len(state['simulation_positions']), 12)
        self.assertEqual(state['tracks'], [])
        self.assertEqual(self.sim.state()['tracks'], [])

    def test_state_and_control_share_replay_clock(self):
        status, _, raw = self.post({"action": "seek", "at_ms": 60000})
        self.assertEqual(status, 200)
        controlled = json.loads(raw)
        status, headers, raw = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), controlled)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, _, raw = self.request("GET", "/api/clock")
        self.assertEqual(status, 200)
        clock = json.loads(raw)
        self.assertEqual(clock["at_ms"], 60000)
        self.assertEqual(clock["run_id"], controlled["run_id"])
        self.assertNotIn("tracks", clock)

    def test_host_origin_and_fetch_metadata_reject_external_control(self):
        for headers in ({"Host": "attacker.example"},
                        {"Origin": "https://attacker.example"},
                        {"Origin": "null"},
                        {"Origin": "http://127.0.0.1:1"},
                        {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                before = self.sim.clock_state()
                self.assertEqual(self.post({"action": "play"}, headers)[0], 403)
                self.assertEqual(self.sim.clock_state(), before)
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "attacker.example"})[0], 403)

    def test_loopback_alias_and_nonbrowser_json_client_are_allowed(self):
        local = f"localhost:{self.server.server_port}"
        self.assertEqual(self.post({"action": "play"}, {"Host": local, "Origin": f"http://{local}"})[0], 200)
        status, _, _ = self.request("POST", "/api/control", json.dumps({"action": "pause"}),
                                    {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertFalse(self.sim.clock_state()["playing"])

    def test_only_explicit_static_assets_are_served(self):
        expected_types = {"/": "text/html", "/app.js": "text/javascript", "/styles.css": "text/css"}
        expected_types.update({'/manifest.webmanifest': 'application/manifest+json',
                               '/notifications.mjs': 'text/javascript', '/sw.js': 'text/javascript',
                               '/pwa-icon.svg': 'image/svg+xml'})
        for path, (_, expected) in self.assets.items():
            with self.subTest(path=path):
                status, headers, body = self.request("GET", path + "?v=1")
                self.assertEqual(status, 200)
                self.assertEqual(body, expected)
                self.assertTrue(headers["Content-Type"].startswith(expected_types[path]))
        for path in ("/private.txt", "/monitor/private.txt", "/../monitor/private.txt",
                     "/%2e%2e/monitor/private.txt", "/data/scenarios/v1/cases/case_001/world.json",
                     "/tools/monitor_server.py", "/index.html", "/app.js/extra"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_config_exposes_case_choices_and_reference_map_without_rubric(self):
        status, _, raw = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertEqual(payload["site"], {"synthetic": True})
        self.assertEqual(payload["regional_map"], {"reference_only": True})
        self.assertEqual(len(payload["cases"]), 3)
        self.assertEqual(set(payload["cases"][0]), {"case_id", "variant"})
        self.assertNotIn("focus_object_id", raw.decode())

    def test_scripted_briefings_are_separate_from_observation_state(self):
        status, _, raw = self.request("GET", "/api/briefings")
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertTrue(payload["author_preview"])
        self.assertEqual(len(payload["cases"]), 3)
        self.assertEqual(payload["cases"][1]["comparison_object"], "object_11")
        state = json.loads(self.request("GET", "/api/state")[2])
        self.assertNotIn("briefings", state)
        self.assertNotIn("comparison_object", json.dumps(state))
        self.assertNotIn("brief.event", json.dumps(state))

    def test_non_json_malformed_oversized_and_invalid_commands_are_rejected(self):
        self.assertEqual(self.request("POST", "/api/control", "action=play",
                                      {"Content-Type": "application/x-www-form-urlencoded"})[0], 415)
        for body in ("{broken", "[]", "null", "", " " * 4097):
            with self.subTest(body=body[:30]):
                self.assertEqual(self.request("POST", "/api/control", body,
                                              {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.post({"action": "seek", "at_ms": True})[0], 400)
        self.assertEqual(self.request("POST", "/missing", "{}",
                                      {"Content-Type": "application/json"})[0], 404)
        self.assertEqual(self.sim.clock_state()["revision"], 0)


if __name__ == "__main__":
    unittest.main()
