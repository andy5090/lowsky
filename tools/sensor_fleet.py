"""Deterministic health-only virtual fleet; never emits detection evidence.

The compact fixture defines logical endpoints and heartbeat timing, independently
of world objects, observation channels and the two physically modeled phone poles.
Only the latest received health record per endpoint is returned.
"""

import json
from pathlib import Path


FIXTURE = Path(__file__).resolve().parents[1] / "data/sensor_fleet_demo.json"
STATUSES = ("online", "offline", "stale", "waiting")


def snapshot(case_id, at_ms, feed=None):
    """Return bounded, time-gated health state without future outage information."""
    if feed is None:
        feed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if case_id not in ("case_001", "case_002", "case_003"):
        raise ValueError("Unknown fleet case")
    duration = feed.get("case_duration_ms", {}).get(case_id, feed["duration_ms"])
    if type(at_ms) is not int or not 0 <= at_ms <= duration:
        raise ValueError("Invalid fleet snapshot time")
    counts = dict.fromkeys(STATUSES, 0)
    groups, sensors = [], []
    interval, delay = feed["heartbeat_interval_ms"], feed["receipt_delay_ms"]
    for group in feed["groups"]:
        # Each group shares a synthetic schedule, keeping fixture and response
        # size proportional to endpoint count rather than heartbeat history.
        observed = ((at_ms - delay) // interval) * interval
        reported_status = "online"
        while observed >= 0:
            interruption = next((event for event in feed["interruptions"]
                                 if event["case_id"] == case_id and event["group_id"] == group["id"]
                                 and event["from_ms"] <= observed < event["until_ms"]), None)
            if interruption and interruption["mode"] == "silent":
                observed -= interval
                continue
            reported_status = "offline" if interruption else "online"
            break
        received = observed + delay if observed >= 0 else None
        status = ("waiting" if received is None else
                  "stale" if at_ms - observed > feed["freshness_ms"] else reported_status)
        group_counts = dict.fromkeys(STATUSES, 0)
        group_counts[status] = group["count"]
        counts[status] += group["count"]
        groups.append({"id": group["id"], "label": dict(group["label"]),
                       "total": group["count"], "counts": group_counts})
        for number in range(1, group["count"] + 1):
            endpoint_id = f"{group['id']}_{number:03d}"
            sensors.append({
                "id": endpoint_id, "group_id": group["id"], "status": status,
                "last_seen_ms": received, "observed_at_ms": observed if received is not None else None,
                "available_at_ms": received,
                "evidence_id": f"fleet_{case_id}_{endpoint_id}_{observed}" if received is not None else None,
                "cause": "unknown" if status in ("offline", "stale", "waiting") else None,
            })
    return {"synthetic": True, "health_only": True, "at_ms": at_ms,
            "total": len(sensors), "freshness_ms": feed["freshness_ms"],
            "counts": counts, "groups": groups, "sensors": sensors}
