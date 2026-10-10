# Tactics layer: target identification, response recommendation, formation and placement optimization

Date: 2026-10-11. Status: implemented under stated assumptions (autonomous session; no interactive approval was available).

## Request

Implement in the current simulation: weapon recommendation (무기 추천), tactical formation (전술 편성), optimized placement of troops, military radar and detection phones (병력·군사용 레이더·탐지폰 배치 최적화), and target identification (표적 식별).

## Context found in the repository

- The local planning documents (`LOW_SKY_scenario_v2.docx`, `LOW_SKY_Detailed_Scenario.docx`, `LOW_SKY_picket_line.docx`) already specify a decoy-vs-attack scoring rubric, an effector allocation table with suitability and cost tiers, a "penalize vs reject" constraint engine (takeoff window, debris zones, own-radar interference), counter-drone team pre-positioning and a P1–P10 picket line. `README.md` and `docs/mvp-direction.md` recorded these as deliberately **not implemented**. This change implements them as a rule-based **training recommendation layer**; the human still confirms, and nothing changes aircraft motion or facility status.
- A previous session left a half-built personnel placement feature: `godot/exercise_units.gd`, the `unit-panel` in `monitor/index.html`, `exerciseUnitCommand` in `monitor/exercise.mjs` and `renderUnits` in `monitor/app.js` exist, but the server had no `units`, `unit_proposal` or `exercise_*_unit*` actions. This design completes that scaffold and generalizes it to four unit kinds.

## Assumptions (made explicit because they could not be asked)

1. Outputs are recommendations with reasons and an explicit confirm step; no engagement, interception or damage model is introduced.
2. Identification uses only received evidence: track kinematics from received observations plus a new synthetic, time-gated **identification report feed** (EO, acoustic, RF classifier outputs) that is built offline from the fixtures with deliberate noise. No world truth or `simulation_visuals` is read at runtime.
3. Effector catalog, costs and suitability follow the scenario documents' public-report ranges and are labeled assumptions.
4. Placement optimization is a deterministic greedy coverage heuristic over the site layout, DEM and OSM road centerlines; it is not a propagation or line-of-sight model.
5. Uncalibrated percentages are not shown; identification is reported as a lean (decoy / attack / indeterminate) with cue list and uncertainty items.

## Data

- `data/tactics/catalog.json`: effectors (`interceptor_drone`, `laser`, `autocannon`, `rf_jammer`) with nominal range, cost tier, per-run inventory, suitability and constraint rules; unit kinds (`infantry`, `radar`, `detection_phone`, `effector_team`) with nominal display range and budgets (12 / 2 / 10 / 4); rubric constants; sector prior weights (north-heavy, labeled scenario prior).
- `data/tactics/identification_demo.json` built by `tools/build_identification_feed.py` from `world.json`, `public.json` and `godot/assets/display_profiles.json`: per case, reports `{id, object_id, sensor_type, observed_at_ms, available_at_ms, fields}` for roughly 35 % of objects (EO), jet acoustic signatures for jet airframes, RF emission for reconnaissance airframes, and a few deliberately conflicting reports in the contradictory case. Reports arrive 15–45 s after the object's first direct receipt.

## Module `tools/tactics.py` (stdlib only)

- `identify(tracks, reports, layout, at_ms)` → per received track: `kinematics` (speed, altitude, heading, heading persistence, descent, closing facility, distance), `group` (neighbors within 600 m on a similar heading), `reports` (arrived identification reports), rubric cues, `lean` ∈ {`decoy_leaning`, `attack_leaning`, `reconnaissance_leaning`, `indeterminate`}, `verification` ∈ {`suspected`, `observed_class`} (never "verified"), `uncertainty[]`, `evidence_ids[]`, `version` digest.
- `recommend(identification, allocations, layout, catalog)` → per track `posture` ∈ {`observe_preserve`, `hold`, `engage_candidate`}, `options[]` each `{effector_id, status ∈ recommended|penalized|rejected, suitability 0–1, reasons[]}`, `primary`, `constraints[]`. Rejections: jammer within 1,500 m of `tower`/`station_a`/`station_b` (own radar), autocannon when debris would fall inside the fence polygon, every effector while the target is over the runway corridor (friendly takeoff surface), zero inventory. Penalties: interceptor vs speed ≥ 300 km/h, interceptor when decoy-leaning (resource preservation), jammer without RF evidence, any effector when no placed `effector_team` covers the target (coverage gap), laser when another laser allocation is active.
- `propose_placement(layout, terrain, context_roads, threat, catalog, budgets)` → deterministic greedy: radar sites maximize weighted sector coverage with an elevation bonus; detection phones take road-side candidates outside the fence in uncovered high-weight sectors (power/comms proxy); effector teams go to the fence ring facing the heaviest sectors with a debris check; infantry fills observation posts at remaining gaps, a QRF near the apron and a patrol on the eastern exterior road. Returns `{id, status:'pending', positions:[{kind, position, label, basis}], coverage, basis}`. `threat` weights come from received tracks' bearings and positive early-signal zones, falling back to the scenario prior.
- `formation(units, identification, catalog)` → teams per sector `{id, role, sector, unit_ids, position, tasking}` and overall `posture`.
- `select_allocation(command, state, catalog)` validates `{run_id, object_id, effector_id, version, confirm}` against current options (not rejected) and inventory, returning a record for the audit log.
- `view(...)` assembles `state['tactics']` with `scope='rule_based_training_advice'`.

## Server (`tools/monitor_server.py`)

- Session state: `units`, `unit_proposal`, `allocations`, cleared whenever `run_id` changes. The initial proposal is computed once per run from the scenario prior.
- New control actions: `exercise_accept_units`, `exercise_manual_units`, `exercise_place_unit` (with `kind`), `exercise_remove_unit`, `exercise_reoptimize_units`, `tactics_allocate`. All require `run_id` and `confirm: true`; positions bounded to ±5,000 m on X/Z with Y = 0.
- `state['exercise']` gains `units`, `unit_proposal`, `unit_kinds`; `state['tactics']` is new. `GET /api/tactics/audit` exports the allocation journal (`.local/tactics-decisions.jsonl`, `--tactics-audit-path`).
- `situation_agent.build_bundle` gains a bounded `tactics` aggregate (counts and postures only) when placements or allocations exist. The agent prompt continues to forbid inventing weapon selection; the summary is labeled rule-based training advice.

## Web (`monitor/`)

- `tactics.mjs`: pure helpers `tacticsCard`, `allocationCommand`, `placementKinds`, `formationRows` with tests in `tests/test_tactics.mjs`.
- Unit panel becomes "Force & sensor placement": proposal summary with kind counts and coverage, Apply / Re-optimize / Choose manually / Place (kind selector) / Cancel; list grouped by kind; map markers per kind with nominal range rings on the site plan.
- New "Target identification & response" panel in the Decisions pane for the selected received track: lean, cues, uncertainty, formation sector, effector option table with status and reasons, Record allocation with a confirm dialog.
- Korean and English copy for every new key; parity test already enforces it.

## Godot (`godot/`)

- `exercise_units.gd` renders four kinds (infantry figure, radar mast, phone pole via `Detailed.make_phone_sensor_pole`, effector team vehicle) with range rings for radar and phones; labels show kind and label.
- Detected drone labels append the identification lean and any recorded allocation from `state['tactics']`.
- `tools/verify_units.gd` extended to cover kinds and label text.

## Tests

- `tests/test_tactics.py`: rubric cases, status semantics (penalize vs reject), runway hold, inventory, placement determinism, bounds, no `world.json` read during `state()`, run reset clearing, audit record shape, agent bundle exclusion of positions.
- `tests/test_exercise.mjs`, `tests/test_tactics.mjs`, `tests/test_monitor_i18n.mjs` for client logic and copy.
- Godot headless `verify_units.gd`; existing suites must stay green.

## Limitations recorded in README

Rule-based, synthetic, uncalibrated; recommendations never alter the scene; identification reports are generated fixtures, not sensor performance; placement coverage rings are display assumptions; effector figures are public-report ranges from the scenario documents.
