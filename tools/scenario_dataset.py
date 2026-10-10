"""Build and inspect synthetic observation-quality scenarios using the stdlib."""

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "v1"
TIMES = (0, 30_000, 60_000, 90_000, 120_000)
SOURCES = ("channel_a", "channel_b")
VARIANTS = ("consistent", "contradictory", "missing")
TTL_MS = 45_000


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build(root):
    """Rebuild only the versioned, generated fixture files; no random state."""
    entries = []
    briefings = []
    layout = read_json(Path(__file__).resolve().parents[1] / "data/site_layout.json")
    scene = {
        "schema_version": "1.0",
        "synthetic": True,
        "coordinates": {"axes": "right-handed, Y-up", "unit": "meter"},
        "interpolation": "linear_between_keyframes",
        "environment": [
            {"id": "ground", "asset_id": "ground_tile", "position": [0, 0, 0]},
            *layout["facilities"],
        ],
    }
    write_json(root / "scene.json", scene)
    for group in range(4):
        objects = [f"object_{group + 1}{i + 1}" for i in range(3)]
        focus = objects[group % 3]
        markers = dict(zip(objects, ("circle", "square", "triangle")))
        world = {
            "schema_version": "1.0", "synthetic": True, "duration_ms": TIMES[-1],
            "objects": [
                {"object_id": obj, "visual": {"asset_id": "aerial_marker", "marker_label": markers[obj]},
                 "keyframes": [
                     {"at_ms": tick, "position": [-300 + i * 300 + group * 10, 100 + i * 10, -1700 - i * 120 + step * 475]}
                     for step, tick in enumerate(TIMES)
                 ]}
                for i, obj in enumerate(objects)
            ],
        }
        for variant_index, variant in enumerate(VARIANTS):
            case_id = f"case_{group * 3 + variant_index + 1:03d}"
            observations, health = [], []
            for tick in TIMES:
                for source in SOURCES:
                    offline = variant == "missing" and source == "channel_b" and tick >= 60_000
                    health.append({
                        "id": f"health_{len(health) + 1:03d}", "source_id": source,
                        "observed_at_ms": tick, "available_at_ms": tick,
                        "status": "offline" if offline else "online",
                    })
                    if offline:
                        continue
                    for obj in objects:
                        marker = markers[obj]
                        if variant == "contradictory" and tick >= 60_000 and obj == focus and source == "channel_b":
                            marker = "diamond"
                        observations.append({
                            "id": f"obs_{len(observations) + 1:03d}", "object_id": obj,
                            "source_id": source, "observed_at_ms": tick, "available_at_ms": tick,
                            "position": next(item for item in world["objects"] if item["object_id"] == obj)["keyframes"][TIMES.index(tick)]["position"],
                            "marker_label": marker,
                        })
            contexts = [
                {"id": "context_001", "published_at_ms": 0,
                 "valid_from_ms": 0, "valid_until_ms": 45_000, "object_ids": [focus],
                 "text": "가상 표시 장치 점검 일정. 관측값의 정확성을 보증하는 자료는 아니다."},
                {"id": "context_002", "published_at_ms": 90_000,
                 "valid_from_ms": 60_000, "valid_until_ms": 120_000, "object_ids": objects,
                 "text": "뒤늦게 공개된 가상 운영 메모. 관측 기록을 다시 확인하도록 요청한다."},
            ]
            public = {
                "schema_version": "1.0", "synthetic": True, "duration_ms": TIMES[-1],
                "object_ids": objects, "source_ids": list(SOURCES), "freshness_ms": TTL_MS,
                "observations": observations, "source_health": health, "contexts": contexts,
            }
            checkpoints = []
            for tick in TIMES[1:]:
                for obj in objects:
                    state = "consistent"
                    if tick >= 60_000:
                        if variant == "missing":
                            state = "missing"
                        elif variant == "contradictory" and obj == focus:
                            state = "contradictory"
                    checkpoints.append({
                        "at_ms": tick, "object_id": obj, "expected_state": state,
                        "required_topics": {
                            "consistent": ["agreement", "source_references", "limits_of_observation"],
                            "contradictory": ["conflicting_marker_labels", "both_sources", "needs_review"],
                            "missing": ["unavailable_source", "last_observation_time", "limits_of_observation"],
                        }[state],
                        "forbidden_claims": ["hostile_intent", "unobserved_confirmation", "future_evidence"],
                    })
            write_json(root / "cases" / case_id / "world.json", world)
            write_json(root / "cases" / case_id / "public.json", public)
            write_json(root / "evaluation" / f"{case_id}.json", {"checkpoints": checkpoints})
            entries.append({"case_id": case_id, "group_id": f"scene_{group + 1:02d}",
                            "split": "development" if group < 2 else "holdout",
                            "variant": variant, "focus_object_id": focus})
            briefings.append({
                "case_id": case_id, "group": group + 1, "variant": variant,
                "object_ids": objects, "duration_ms": TIMES[-1], "sample_interval_ms": TIMES[1],
                "source_ids": list(SOURCES),
                "comparison_object": focus if variant == "contradictory" else None,
                "original_marker": markers[focus] if variant == "contradictory" else None,
                "timeline": [
                    {"at_ms": 0, "key": "brief.start"},
                    {"at_ms": TIMES[1], "key": "brief.samples"},
                    {"at_ms": TIMES[2], "key": f"brief.event.{variant}"},
                    {"at_ms": TIMES[3], "key": "brief.context"},
                    {"at_ms": TIMES[4], "key": "brief.end"},
                ],
            })
    write_json(root / "briefings.json", {
        "schema_version": "1.0", "synthetic": True, "author_preview": True,
        "purpose": "Operator-requested scripted scenario overview, including future events. Not live evidence or agent input.",
        "cases": briefings,
    })
    write_json(root / "manifest.json", {
        "schema_version": "1.0", "synthetic": True,
        "purpose": "3D replay and explanation-quality smoke evaluation",
        "generation": "deterministic; tools/scenario_dataset.py; no external sources",
        "cases": entries,
    })


def snapshot(public, at_ms):
    """Allowlist agent inputs, excluding future records and author-only data."""
    require(type(at_ms) is int and 0 <= at_ms <= public["duration_ms"], "Invalid snapshot time")
    observation_keys = ("id", "object_id", "source_id", "observed_at_ms", "available_at_ms", "position", "marker_label")
    health_keys = ("id", "source_id", "observed_at_ms", "available_at_ms", "status")
    context_keys = ("id", "published_at_ms", "valid_from_ms", "valid_until_ms", "object_ids", "text")
    return {
        "schema_version": "1.0", "synthetic": True, "at_ms": at_ms,
        "object_ids": list(public["object_ids"]), "source_ids": list(public["source_ids"]),
        "freshness_ms": public["freshness_ms"],
        "observations": [
            {key: record[key] for key in observation_keys} for record in public["observations"]
            if record["available_at_ms"] <= at_ms and record["observed_at_ms"] <= at_ms
        ],
        "source_health": [
            {key: record[key] for key in health_keys} for record in public["source_health"]
            if record["available_at_ms"] <= at_ms and record["observed_at_ms"] <= at_ms
        ],
        # Known schedules may concern the future; publication time gates knowledge.
        "contexts": [
            {key: record[key] for key in context_keys} for record in public["contexts"]
            if record["published_at_ms"] <= at_ms
        ],
    }


def information_state(payload, object_id):
    """Fixture baseline: same-time marker agreement, no object classification."""
    require(object_id in payload["object_ids"], "Unknown object")
    latest = []
    for source in payload["source_ids"]:
        health = [row for row in payload["source_health"] if row["source_id"] == source]
        rows = [row for row in payload["observations"]
                if row["source_id"] == source and row["object_id"] == object_id]
        status = max(health, key=lambda row: (row["observed_at_ms"], row["available_at_ms"]), default=None)
        row = max(rows, key=lambda item: (item["observed_at_ms"], item["available_at_ms"]), default=None)
        if (status is None or status["status"] != "online" or row is None
                or payload["at_ms"] - row["observed_at_ms"] > payload["freshness_ms"]
                or payload["at_ms"] - status["observed_at_ms"] > payload["freshness_ms"]):
            return "missing"
        latest.append(row)
    if len({row["observed_at_ms"] for row in latest}) != 1:
        return "not_comparable"
    return "consistent" if len({row["marker_label"] for row in latest}) == 1 else "contradictory"


def validate(root):
    manifest = read_json(root / "manifest.json")
    entries = manifest["cases"]
    scene = read_json(root / "scene.json")
    require(scene["coordinates"]["unit"] == "meter", "Invalid coordinate units")
    require(all(item.get("asset_id") for item in scene["environment"]), "Missing scene asset mapping")
    require(len(entries) == 12, "Expected 12 starter cases")
    require(len({entry["case_id"] for entry in entries}) == len(entries), "Duplicate case IDs")
    groups = {}
    observation_count = checkpoint_count = 0
    for entry in entries:
        case_id = entry["case_id"]
        groups.setdefault(entry["group_id"], []).append(entry)
        public = read_json(root / "cases" / case_id / "public.json")
        world = read_json(root / "cases" / case_id / "world.json")
        rubric = read_json(root / "evaluation" / f"{case_id}.json")
        require(public["schema_version"] == world["schema_version"] == "1.0", "Invalid schema version")
        require(public["synthetic"] is True and world["synthetic"] is True, "Missing synthetic label")
        require(public["duration_ms"] == world["duration_ms"] == TIMES[-1], "Invalid duration")
        require(public["source_ids"] == list(SOURCES), "Unexpected source IDs")
        require(public["freshness_ms"] == TTL_MS, "Unexpected freshness setting")
        require(len(set(public["object_ids"])) == 3, "Expected three unique objects")
        require(entry["split"] in ("development", "holdout"), "Unknown split")
        require({obj["object_id"] for obj in world["objects"]} == set(public["object_ids"]), "Object mismatch")
        ids = set()
        records = public["observations"] + public["source_health"] + public["contexts"]
        for row in records:
            require(row["id"] not in ids, f"Duplicate evidence ID in {case_id}")
            ids.add(row["id"])
            if "source_id" in row:
                require(row["source_id"] in SOURCES, "Unknown source")
                observed, available = row["observed_at_ms"], row["available_at_ms"]
                require(type(observed) is int and type(available) is int
                        and 0 <= observed <= available <= TIMES[-1], "Invalid observation time")
            if "object_id" in row:
                require(row["object_id"] in public["object_ids"], "Unknown observed object")
                require(row["marker_label"] in ("circle", "square", "triangle", "diamond"), "Invalid marker")
            if "status" in row:
                require(row["status"] in ("online", "offline"), "Invalid channel status")
            if "published_at_ms" in row:
                require(set(row["object_ids"]) <= set(public["object_ids"]), "Unknown context object")
                require(0 <= row["published_at_ms"] <= TIMES[-1]
                        and 0 <= row["valid_from_ms"] <= row["valid_until_ms"] <= TIMES[-1], "Invalid context time")
        positions = [row["position"] for row in public["observations"]]
        for obj in world["objects"]:
            require(obj["visual"]["asset_id"] == "aerial_marker", "Missing object asset mapping")
            require([row["at_ms"] for row in obj["keyframes"]] == list(TIMES), "Invalid keyframe times")
            positions.extend(row["position"] for row in obj["keyframes"])
        for position in positions:
            require(len(position) == 3 and all(type(v) in (int, float) and math.isfinite(v) for v in position), "Invalid 3D position")
        require(len(rubric["checkpoints"]) == 12, "Expected twelve checkpoints")
        expected_pairs = {(tick, obj) for tick in TIMES[1:] for obj in public["object_ids"]}
        require({(row["at_ms"], row["object_id"]) for row in rubric["checkpoints"]} == expected_pairs,
                "Checkpoint coverage mismatch")
        for checkpoint in rubric["checkpoints"]:
            payload = snapshot(public, checkpoint["at_ms"])
            actual = information_state(payload, checkpoint["object_id"])
            require(actual == checkpoint["expected_state"], f"State mismatch in {case_id}: {checkpoint}")
            require(checkpoint["required_topics"] and checkpoint["forbidden_claims"], "Missing review rubric")
        observation_count += len(public["observations"])
        checkpoint_count += len(rubric["checkpoints"])
    require(len(groups) == 4, "Expected four scene groups")
    for group, members in groups.items():
        require(len({member["split"] for member in members}) == 1, f"Split leakage: {group}")
        require({member["variant"] for member in members} == set(VARIANTS), f"Missing variants: {group}")
        worlds = [read_json(root / "cases" / member["case_id"] / "world.json") for member in members]
        require(all(world == worlds[0] for world in worlds), f"Variant changed world: {group}")
    return {"cases": len(entries), "scene_groups": len(groups),
            "observations": observation_count, "checkpoints": checkpoint_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate", "snapshot"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--case", default="case_001")
    parser.add_argument("--at-ms", type=int, default=60_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build(args.root)
        print(json.dumps(validate(args.root)))
    elif args.command == "validate":
        print(json.dumps(validate(args.root)))
    else:
        entries = read_json(args.root / "manifest.json")["cases"]
        require(args.case in {entry["case_id"] for entry in entries}, "Unknown case")
        payload = snapshot(read_json(args.root / "cases" / args.case / "public.json"), args.at_ms)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result = {"snapshot_id": digest, **payload}
        if args.output:
            write_json(args.output, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
