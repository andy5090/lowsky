"""Build and inspect synthetic observation-quality scenarios using the stdlib."""

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "v1"
TIMES = tuple(range(0, 180_001, 10_000))
SOURCES = ("channel_a", "channel_b")
VARIANTS = ("consistent", "contradictory", "missing")
WORKLOAD_COUNTS = (48, 96, 240)
TTL_MS = 45_000
DISPLAY_PROFILES = Path(__file__).resolve().parents[1] / "godot/assets/display_profiles.json"
PACED_OFFSET_MS = 240_000
PACED_SCALE = 3
PACED_DURATION_MS = PACED_OFFSET_MS + PACED_SCALE * TIMES[-1]


def authored_time(variant, at_ms):
    return at_ms if variant == "missing" else PACED_OFFSET_MS + PACED_SCALE * at_ms


def distant_display_z(at_ms):
    """Schematic northern approach only; never a georeferenced crossing route."""
    if at_ms <= 270_000:
        return -18_000 + (at_ms / 270_000) * 15_800
    return -2200 + ((at_ms - 270_000) / (PACED_DURATION_MS - 270_000)) * 4100


def training_timing(variant):
    paced = variant != "missing"
    return {"paced": paced, "early_review_ms": 120_000 if paced else 30_000,
            "received_review_ms": 90_000 if paced else 30_000}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def localized(en, ko):
    return {"en": en, "ko": ko}


def build(root):
    """Rebuild the three deterministic representative workload fixtures."""
    entries, briefings = [], []
    layout = read_json(Path(__file__).resolve().parents[1] / "data/site_layout.json")
    airframes = tuple(read_json(DISPLAY_PROFILES)["airframes"])
    write_json(root / "scene.json", {
        "schema_version": "1.0", "synthetic": True,
        "coordinates": {"axes": "right-handed, Y-up", "unit": "meter"},
        "interpolation": "linear_between_keyframes",
        "environment": [{"id": "ground", "asset_id": "ground_tile", "position": [0, 0, 0]}, *layout["facilities"], *layout.get("field_installations", [])],
    })
    first_count, second_count, _ = WORKLOAD_COUNTS
    conflicting_count = len(range(0, second_count, 4))
    descriptions = [
        (
            localized("Indicators and first reports", "전조와 첫 관측"),
            localized(f"02:00 AM · Fictional northern Gyeonggi base, possible arrival from the North Korean side. {first_count} synthetic objects; review indirect indications before direct reports at 04:30.", f"오전 02:00 · 경기 북부 가상 기지, 북측 유입 가능성. 합성 비행체 {first_count}대. 04:30 직접 관측 전까지 간접 조짐을 검토합니다."),
            localized("Separate first receipt, observation time and corroboration; an observed track does not establish identity or intent.", "최초 수신·관측 시각·교차 확인을 구분합니다. 탐지만으로 정체나 의도를 확정하지 않습니다."),
            localized(f"{first_count} small aerial objects with three synthetic marker classes; labels are observations, not hostile or civilian classifications.", f"소형 비행체 {first_count}대와 세 가지 합성 표식. 표식은 관측값이며 적대·민간 분류가 아닙니다."),
        ),
        (
            localized("Conflicting evidence and review", "상충 근거와 검토"),
            localized(f"02:00 AM · Fictional northern Gyeonggi base, possible arrival from the North Korean side. {second_count} synthetic objects; indirect indications followed by conflicting reports and review.", f"오전 02:00 · 경기 북부 가상 기지, 북측 유입 가능성. 합성 비행체 {second_count}대. 간접 조짐 이후 상충 보고와 재검토가 이어집니다."),
            localized("Preserve both sources and compare timestamps before resolving a label disagreement; review the return to agreement.", "표식 불일치를 판단하기 전에 양측 근거와 시각을 보존하고, 보고가 다시 일치하는 과정을 검토합니다."),
            localized(f"{second_count} synthetic objects; {conflicting_count} conflicting tracks, with the remaining tracks as comparison traffic.", f"합성 비행체 {second_count}대. {conflicting_count}대에서 상충 보고가 발생하고 나머지는 비교 대상입니다."),
        ),
        (
            localized("Monitoring load test: source loss and recovery", "모니터링 부하 시험: 채널 단절·복구"),
            localized("240 synthetic aerial objects exercise the review queue. Channel B is unavailable from 01:00 until 02:10 and then resumes reporting.", "합성 비행체 240개로 검토 대기열을 시험합니다. 채널 B는 01:00부터 02:10까지 단절된 뒤 보고를 재개합니다."),
            localized("Retain last evidence during loss, distinguish missing corroboration from disappearance, and verify recovery without inventing tracks.", "단절 중 마지막 근거를 보존하고 교차 확인 불가와 대상 소멸을 구분하며, 근거를 만들어내지 않고 복구를 확인합니다."),
            localized("240 synthetic objects sharing two observation channels, plus an independent health-only fleet of 240 virtual sensor endpoints. These are workload assumptions, not measured attack or deployment sizes.", "합성 비행체 240개가 두 관측 채널을 공유하며, 별도의 가상 센서 240개는 상태 정보만 제공합니다. 수량은 부하 시험 가정이며 실측 공격·배치 규모가 아닙니다."),
        ),
    ]
    for index, (variant, count) in enumerate(zip(VARIANTS, WORKLOAD_COUNTS)):
        case_id = f"case_{index + 1:03d}"
        objects = [f"object_{11 + i:02d}" for i in range(count)]
        markers = {obj: ("circle", "square", "triangle")[i % 3] for i, obj in enumerate(objects)}
        # Keep the larger generic workload inside the same preview extent. This
        # grid is a display fixture, not a formation or attack-path model.
        columns, row_spacing = (12, 16) if variant == "missing" else (6, 80)
        column_spacing = 1500 / 11 if variant == "missing" else 300
        world = {
            "schema_version": "1.0", "synthetic": True, "duration_ms": TIMES[-1],
            "objects": [
                {"object_id": obj, "visual": {"asset_id": "aerial_marker", "marker_label": markers[obj],
                                              "airframe_id": airframes[i % len(airframes)]},
                 "keyframes": [
                     {"at_ms": tick, "position": [
                         -750 + (i % columns) * column_spacing + (tick / TIMES[-1]) * (80 if i % 2 else -80),
                         80 + (i % 5) * 12,
                         -1900 - (i // columns) * row_spacing + (tick / TIMES[-1]) * 3800,
                     ]} for tick in TIMES]}
                for i, obj in enumerate(objects)
            ],
        }
        observations, health = [], []
        for step, tick in enumerate(TIMES):
            for source in SOURCES:
                offline = variant == "missing" and source == "channel_b" and 60_000 <= tick < 130_000
                health.append({"id": f"health_{len(health) + 1:03d}", "source_id": source,
                               "observed_at_ms": tick, "available_at_ms": tick,
                               "status": "offline" if offline else "online"})
                if offline:
                    continue
                for i, obj in enumerate(objects):
                    first_tick = 10_000 + (i % 6) * 10_000
                    if tick < first_tick:
                        continue
                    delay = 4_000 if source == "channel_b" and tick == first_tick else 0
                    if source == "channel_b" and tick == 40_000 and i % 4 == 0:
                        delay = 15_000
                    marker = markers[obj]
                    if variant == "contradictory" and source == "channel_b" and 60_000 <= tick <= 120_000 and i % 4 == 0:
                        marker = "diamond"
                    observations.append({
                        "id": f"obs_{len(observations) + 1:04d}", "object_id": obj,
                        "source_id": source, "observed_at_ms": tick, "available_at_ms": tick + delay,
                        "position": world["objects"][i]["keyframes"][step]["position"], "marker_label": marker,
                    })
        contexts = [
            {"id": "context_001", "published_at_ms": 0, "valid_from_ms": 0,
             "valid_until_ms": 45_000, "object_ids": [objects[0]],
             "text": "Synthetic display inspection notice. It does not confirm the accuracy or identity of an observed object."},
            {"id": "context_002", "published_at_ms": 90_000, "valid_from_ms": 60_000,
             "valid_until_ms": TIMES[-1], "object_ids": objects,
             "text": "Delayed synthetic review notice: compare received evidence and source health; do not infer intent."},
        ]
        public = {
            "schema_version": "1.0", "synthetic": True, "duration_ms": TIMES[-1],
            "object_ids": objects, "source_ids": list(SOURCES), "freshness_ms": TTL_MS,
            "observations": observations, "source_health": health, "contexts": contexts,
        }
        # Expectations are authored from the scenario events, independently of information_state.
        checkpoints = []
        for tick in (70_000, 90_000, 120_000, 150_000, 180_000):
            for i, obj in enumerate(objects):
                state = "consistent"
                if tick <= 120_000:
                    if variant == "missing":
                        state = "missing"
                    elif variant == "contradictory" and i % 4 == 0:
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
        public["training_timing"] = training_timing(variant)
        if variant != "missing":
            duration = PACED_DURATION_MS
            world["duration_ms"] = public["duration_ms"] = duration
            public["freshness_ms"] = TTL_MS * PACED_SCALE
            # Motion uses the same authored replay clock, continuously across the
            # indirect-only period; evidence never exposes these hidden positions.
            for i, obj in enumerate(world["objects"]):
                obj["keyframes"] = [{"at_ms": tick, "position": [
                    -750 + (i % columns) * column_spacing + (tick / duration) * (80 if i % 2 else -80),
                    80 + (i % 5) * 12,
                    distant_display_z(tick) - (i // columns) * row_spacing,
                ]} for tick in range(0, duration + 1, 10_000)]
            frames = {obj["object_id"]: {frame["at_ms"]: frame["position"] for frame in obj["keyframes"]}
                      for obj in world["objects"]}
            for row in observations:
                for key in ("observed_at_ms", "available_at_ms"):
                    row[key] = authored_time(variant, row[key])
                row["position"] = frames[row["object_id"]][row["observed_at_ms"]]
            public["source_health"] = [
                {"id": f"health_{step * len(SOURCES) + index + 1:03d}", "source_id": source,
                 "observed_at_ms": tick, "available_at_ms": tick, "status": "online"}
                for step, tick in enumerate(range(0, duration + 1, 10_000))
                for index, source in enumerate(SOURCES)]
            for row in contexts:
                for key in ("published_at_ms", "valid_from_ms", "valid_until_ms"):
                    if row[key] > 0:
                        row[key] = authored_time(variant, row[key])
            for row in checkpoints:
                row["at_ms"] = authored_time(variant, row["at_ms"])
        duration = public["duration_ms"]
        public["training_schedule"] = {
            "author_preview": True,
            "first_direct_observation_ms": authored_time(variant, 10_000),
            "phases": ([
                {"id": "indirect_review", "label": localized("Indirect indications and deliberation", "간접 징후와 숙고"), "start_ms": 0, "end_ms": 270_000},
                {"id": "initial_receipts", "label": localized("Initial direct receipts", "직접 관측 최초 수신"), "start_ms": 270_000, "end_ms": 420_000},
                {"id": "compare_evidence", "label": localized("Compare received evidence", "수신 근거 비교"), "start_ms": 420_000, "end_ms": 630_000},
                {"id": "reconsider_review", "label": localized("Reconsider and record review", "재검토와 판단 기록"), "start_ms": 630_000, "end_ms": duration},
            ] if variant != "missing" else [
                {"id": "compact_load", "label": localized("Compact load test", "압축 부하 시험"), "start_ms": 0, "end_ms": duration}])}
        write_json(root / "cases" / case_id / "world.json", world)
        write_json(root / "cases" / case_id / "public.json", public)
        write_json(root / "evaluation" / f"{case_id}.json", {"checkpoints": checkpoints})
        entries.append({"case_id": case_id, "group_id": f"scene_{index + 1:02d}",
                        "split": "development", "variant": variant, "focus_object_id": objects[0]})
        name, summary, objective, composition = descriptions[index]
        event = {
            "consistent": localized(f"All {count} candidates have a first report; corroboration may still be pending.", f"{count}대의 최초 보고가 수신되며 일부 교차 확인은 대기 중입니다."),
            "contradictory": localized(f"Channel B begins conflicting labels on {conflicting_count} tracks.", f"채널 B에서 {conflicting_count}대의 표식 상충이 시작됩니다."),
            "missing": localized("Channel B stops reporting. Preserve the last received evidence.", "채널 B의 보고가 중단됩니다. 마지막 수신 근거를 보존합니다."),
        }[variant]
        briefings.append({
            "case_id": case_id, "group": index + 1, "variant": variant,
            "scenario_type": "load_test" if variant == "missing" else "observation_narrative",
            "context_feed": "data/situation_review.json",
            "adaptation": "Non-operational observation and human review themes from LOW_SKY_Detailed_Scenario.docx; no attack sequence or response model.",
            "name": name, "summary": summary, "objective": objective, "composition": composition,
            "count_basis": localized("Object counts are synthetic scene assumptions, not measured attack sizes; only case_003 is a load test.", "대상 수는 장면 구성을 위한 합성 가정이며 실측 공격 규모가 아닙니다. 부하 시험은 case_003만 해당합니다."),
            "object_count": count, "object_ids": objects, "duration_ms": duration,
            "training_timing": public["training_timing"], "training_schedule": public["training_schedule"],
            "sample_interval_ms": 10_000 if variant == "missing" else 30_000, "source_ids": list(SOURCES),
            "comparison_object": objects[0] if variant == "contradictory" else None,
            "original_marker": markers[objects[0]] if variant == "contradictory" else None,
            "timeline": [
                {"at_ms": 0, "text": localized("Replay begins with no received tracks.", "수신된 대상 없이 재생을 시작합니다.")},
                {"at_ms": 10_000, "text": localized("First receipt; further candidates appear in staggered batches.", "첫 탐지 수신 후 대상이 순차 등장합니다.")},
                {"at_ms": 40_000, "text": localized("Some channel B reports arrive 15 seconds late; compare observation and receipt time.", "일부 채널 B 보고가 15초 늦게 도착합니다. 관측·수신 시각을 비교합니다.")},
                {"at_ms": 60_000, "text": event},
                {"at_ms": 90_000, "text": localized("A previously unpublished review notice becomes available.", "공개되지 않았던 검토 공지가 수신됩니다.")},
                {"at_ms": 130_000, "text": localized("Both channels provide agreeing reports; review outstanding alerts.", "두 채널이 일치하는 보고를 제공합니다. 남은 경고를 검토합니다.")},
                {"at_ms": TIMES[-1], "text": localized("Replay ends; assess evidence references, uncertainty and source recovery.", "재생 종료 후 근거 참조·불확실성·채널 복구를 평가합니다.")},
            ],
        })
        if variant != "missing":
            for step in briefings[-1]["timeline"]:
                if step["at_ms"] > 0:
                    step["at_ms"] = authored_time(variant, step["at_ms"])
            briefings[-1]["timeline"][2]["text"] = localized(
                "Some channel B reports arrive 45 seconds late; compare observation and receipt time.",
                "일부 채널 B 보고가 45초 늦게 도착합니다. 관측·수신 시각을 비교합니다.")
            briefings[-1]["origin_context"] = localized(
                "Fictional reports suggest possible arrival from the North Korean side. Origin and any border crossing are unconfirmed; the distant northern departure area and paths are schematic, not real georeferenced routes.",
                "북측에서 유입될 가능성을 시사하는 가상 제보입니다. 출발지와 국경 통과는 미확인이며 원거리 북쪽 출발 구역과 경로는 실제 지리 좌표가 아닌 개념도입니다.")
            briefings[-1]["timeline"][0]["text"] = localized(
                "Replay begins with no received tracks. Author motion starts in a fictional distant northern departure area, with no verified origin or border crossing.",
                "수신 항적 없이 시작합니다. 제작용 움직임은 원거리 가상 북쪽 출발 구역에서 시작하며 실제 출발지나 국경 통과는 확인되지 않습니다.")
            briefings[-1]["timeline"][1:1] = [
                {"at_ms": 30_000, "text": localized("One indirect area indication arrives; no direct track or object identity is established.", "구역 단위 간접 징후가 하나 수신됩니다. 직접 항적이나 대상 정체는 확정되지 않습니다.")},
                {"at_ms": 150_000, "text": localized("After two minutes of a stable single-source question, an independent delayed report becomes available; it may agree or conflict.", "동일한 단일 출처 징후를 2분 동안 검토한 뒤 독립 지연 보고가 수신됩니다. 일치하거나 상충할 수 있습니다.")},

                {"at_ms": 200_000, "text": localized("An independent area report is stale. Missing fresh evidence does not establish absence.", "별도 구역 보고가 오래되었습니다. 새 근거가 없다는 사실로 부재를 확정하지 않습니다.")},
                {"at_ms": 225_000, "text": localized("A negative measurement and independent fixed-phone indications require reconsideration; they do not identify a hidden object.", "음성 측정과 독립 고정 폰 징후를 토대로 재검토합니다. 보이지 않는 대상의 정체나 위치는 식별하지 못합니다.")},
            ]
    # Remove only retired generated files from the original twelve-case fixture set.
    for number in range(4, 13):
        retired = root / "cases" / f"case_{number:03d}"
        for filename in ("world.json", "public.json"):
            (retired / filename).unlink(missing_ok=True)
        if retired.exists() and not any(retired.iterdir()):
            retired.rmdir()
        (root / "evaluation" / f"case_{number:03d}.json").unlink(missing_ok=True)
    write_json(root / "briefings.json", {
        "schema_version": "1.0", "synthetic": True, "author_preview": True,
        "purpose": "Scripted scenario overview includes future events; not live evidence or agent input.", "cases": briefings,
    })
    write_json(root / "manifest.json", {
        "schema_version": "1.0", "synthetic": True,
        "purpose": "Two synthetic observation narratives and one monitoring load test; not an empirical threat model",
        "generation": "deterministic; tools/scenario_dataset.py; no external sources", "cases": entries,
    })


def snapshot(public, at_ms):
    """Allowlist agent inputs, excluding future records and author-only data."""
    require(type(at_ms) is int and 0 <= at_ms <= public["duration_ms"], "Invalid snapshot time")
    observation_keys = ("id", "object_id", "source_id", "observed_at_ms", "available_at_ms", "position", "marker_label")
    health_keys = ("id", "source_id", "observed_at_ms", "available_at_ms", "status")
    context_keys = ("id", "published_at_ms", "valid_from_ms", "valid_until_ms", "object_ids", "text")
    observations = [
        {key: record[key] for key in observation_keys} for record in public["observations"]
        if record["available_at_ms"] <= at_ms and record["observed_at_ms"] <= at_ms
        and record.get("detected", True) is True
    ]
    received_ids = {row["object_id"] for row in observations}
    contexts = []
    for record in public["contexts"]:
        if record["published_at_ms"] > at_ms:
            continue
        # Withhold the entire object-specific notice until every referenced ID is known;
        # filtering IDs alone could still leak an unseen ID mentioned in its free text.
        if not set(record["object_ids"]) <= received_ids:
            continue
        contexts.append({key: record[key] for key in context_keys})
    return {
        "schema_version": "1.0", "synthetic": True, "at_ms": at_ms,
        "object_ids": [obj for obj in public["object_ids"] if obj in received_ids], "source_ids": list(public["source_ids"]),
        "freshness_ms": public["freshness_ms"],
        "observations": observations,
        "source_health": [
            {key: record[key] for key in health_keys} for record in public["source_health"]
            if record["available_at_ms"] <= at_ms and record["observed_at_ms"] <= at_ms
        ],
        "contexts": contexts,
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
    require(len(entries) == 3, "Expected three representative cases")
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
        duration = authored_time(entry["variant"], TIMES[-1])
        require(public["duration_ms"] == world["duration_ms"] == duration, "Invalid duration")
        require(public["source_ids"] == list(SOURCES), "Unexpected source IDs")
        require(public["freshness_ms"] == TTL_MS * (1 if entry["variant"] == "missing" else PACED_SCALE), "Unexpected freshness setting")
        require(len(set(public["object_ids"])) == WORKLOAD_COUNTS[VARIANTS.index(entry["variant"])], "Unexpected workload count")
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
                        and 0 <= observed <= available <= duration, "Invalid observation time")
            if "object_id" in row:
                require(row["object_id"] in public["object_ids"], "Unknown observed object")
                require(row["marker_label"] in ("circle", "square", "triangle", "diamond"), "Invalid marker")
            if "status" in row:
                require(row["status"] in ("online", "offline"), "Invalid channel status")
            if "published_at_ms" in row:
                require(set(row["object_ids"]) <= set(public["object_ids"]), "Unknown context object")
                require(0 <= row["published_at_ms"] <= duration
                        and 0 <= row["valid_from_ms"] <= row["valid_until_ms"] <= duration, "Invalid context time")
        positions = [row["position"] for row in public["observations"]]
        for obj in world["objects"]:
            require(obj["visual"]["asset_id"] == "aerial_marker", "Missing object asset mapping")
            require([row["at_ms"] for row in obj["keyframes"]] == list(range(0, duration + 1, 10_000)), "Invalid keyframe times")
            positions.extend(row["position"] for row in obj["keyframes"])
        for position in positions:
            require(len(position) == 3 and all(type(v) in (int, float) and math.isfinite(v) for v in position), "Invalid 3D position")
        require(len(rubric["checkpoints"]) == len(public["object_ids"]) * 5, "Unexpected checkpoint count")
        checkpoint_times = [authored_time(entry["variant"], tick) for tick in (70_000, 90_000, 120_000, 150_000, 180_000)]
        expected_pairs = {(tick, obj) for tick in checkpoint_times for obj in public["object_ids"]}
        require({(row["at_ms"], row["object_id"]) for row in rubric["checkpoints"]} == expected_pairs,
                "Checkpoint coverage mismatch")
        checkpoint_payloads = {tick: snapshot(public, tick) for tick in checkpoint_times}
        for checkpoint in rubric["checkpoints"]:
            payload = checkpoint_payloads[checkpoint["at_ms"]]
            actual = information_state(payload, checkpoint["object_id"])
            require(actual == checkpoint["expected_state"], f"State mismatch in {case_id}: {checkpoint}")
            require(checkpoint["required_topics"] and checkpoint["forbidden_claims"], "Missing review rubric")
        observation_count += len(public["observations"])
        checkpoint_count += len(rubric["checkpoints"])
    require(len(groups) == 3, "Expected three independent scenario groups")
    require({entry["variant"] for entry in entries} == set(VARIANTS), "Missing representative condition")
    require(all(entry["split"] == "development" for entry in entries), "Demo scenarios are not a holdout benchmark")
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
