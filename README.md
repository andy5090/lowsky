# LOW SKY — Fictional Airfield Scenario Lab

[한국어](README.ko.md)

<img src="monitor/logo-metal.png" alt="LOW SKY metallic aviation emblem" width="144" height="144">

LOW SKY combines a Godot 3D authoring view with a separate web **Decision making workspace**, synchronized to one replay clock. The setting is a fictional airfield on a Korean map background, with a separate site plan and a photorealistic art direction. The workspace now includes overall situation assessment, received-evidence explanations and human review. Deep Agents is an optional LLM adapter; without provider configuration the interface explicitly shows a rule-based overview.

Original planning documents remain local and are excluded from the public repository. See [MVP direction](docs/mvp-direction.md) for scope and the folders under `godot/third_party/` for asset licenses and provenance.

## Included

- [Scenario dataset](data/scenarios/v1/README.md): three 180-second cases with 12, 24, and 240 objects; 6,876 observations and 1,380 evaluation checkpoints. Only the third case is a load test.
- [Drone/source catalog](data/references/drone_sources.json): nine user-supplied names/categories and ten sources, separate from executable scenarios and not individually verified.
- [Drone scenario extension](docs/drone-scenario-extension.md): size, role, and communication concepts.
- `monitor/`: English by default, optional Korean, scenario briefings, received observations, evidence, current alerts, human review, and PWA notifications.
- `tools/monitor_server.py`: Python standard-library local server and shared clock.
- `data/site_layout.json`: a fictional 2,500 × 45 m runway, irregular 12-vertex site within a 1,200 × 2,900 m bounding box, and a 2.5 m perimeter fence. These are visualization assumptions, not a reproduced base or certified design.
- `data/terrain/korea_site.json`: public elevation data around an arbitrary Korean reference point, 36.23° N, 127.08° E, sampled over 10 × 10 km at 50 m spacing.
- `godot/assets/`: seven generated placeholder GLBs and asset mappings.
- `godot/third_party/kenney_industrial/`: four candidate models, textures, original license, and provenance.
- `godot/third_party/realistic/`: four PBR material sets, HDRI sky, and a Cesium aircraft sample with licenses and hashes.
- `godot/detailed_environment.gd`, `godot/plains_environment.gd`, and `godot/preview.gd`: procedural buildings, terrain presets, asset previews, and scenario replay.

## Run

Tested with Godot 4.5. Open `godot/project.godot` in the editor, or on macOS:

```sh
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```

For synchronized monitoring and 3D, start the server first:

```sh
python3 tools/monitor_server.py
# In another terminal:
/Applications/Godot.app/Contents/MacOS/Godot --path godot -- --monitor
```

Open http://127.0.0.1:8765. The language selector stores the choice in this browser. Monitor play, pause, seek, case selection, and speed control the shared replay. `--monitor` disables Godot's replay controls while keeping camera and terrain controls available. Godot pauses on disconnection and resynchronizes when the connection returns. The web play button does not launch Godot; open the 3D window separately.

The synchronized view starts at the overview. By default, 3D labels and screen markers appear only for fresh received detections. **Show drone positions (SIM)** is off initially; turn it on to label every simulated drone in purple, including undetected objects. Physical drone bodies continue moving in the 3D simulation. The map has its own **Show drone positions** switch, also off initially, with a separate purple truth layer and warning. These switches are independent display preferences. **F / Follow first drone** toggles between following the first drone and the overview; manual camera movement cancels follow mode. The drone model keeps its provisional **0.6 m maximum horizontal span, including propellers**. Profiles live in `godot/assets/display_profiles.json`, selected by each object's `visual.size_profile`.

Without the server, Godot runs independently:

| Control | Action |
| --- | --- |
| 1 / 2 / 3 | Select a scenario branch |
| Space / R | Pause or resume / restart |
| Left or middle drag | Pan |
| Right or Shift + left drag | Orbit |
| Mouse wheel / left-right arrows | Zoom / rotate |
| C / H | Close-up or overview / reset camera |
| T / Terrain | Korean DEM → synthetic plains → synthetic hills |

Start drags outside the control panel. `-- --plains` and `-- --hills` choose synthetic terrain presets; `-- --stylized` and `-- --blockout` select alternative assets. Terrain switching preserves the replay. The scene is an early photorealistic prototype; final environment art and aircraft replacement remain unfinished.

## Observations and replay

Godot is an **authoring view** showing simulated object movement even when observations stop. By default, the map and 3D labels show only fresh received detections. When evidence expires or its sources go offline, map markers and 3D labels disappear; the evidence list retains the last report and timestamp. Explicit negative detection rows (`detected: false`) do not reveal objects. The optional **Show drone positions** layer requests `/api/state?show_positions=1`, which returns separate `simulation_positions` at that same replay time. Truth never becomes an observation, alert, or review input; switching off or reloading hides it. Positions come from synthetic samples, normally ten seconds apart; delayed reports remain hidden until `available_at_ms`. All cases begin with no received tracks; first reports arrive at 00:10, and objects appear progressively through 01:00. Detection does not establish hostile intent.

Contradiction, channel loss, and stale-position alerts describe observation quality. Channels A/B are not physical RF or fiber models. Acknowledgements apply to the current run, clear on seek/reset/case change, and disappear when the server restarts. At most 1,000 acknowledgement records remain in server memory; this is not a permanent audit log.

**Scenario briefing** and **Timeline & review points** explain purpose, object count, milestones, and review criteria. The cases cover first reports (12 objects), conflicting evidence and review (24), and monitoring load with channel interruption/recovery (240). Counts and routes are synthetic assumptions, not measured attack sizes. Briefings contain future events for the operator and are served separately by `/api/briefings`; received-only state and clock use `/api/state` and `/api/clock`. Area early signals are a separate feed shared by all cases.

**Radar overlay** animates received observations from A/B. Scans follow the shared clock and stop for paused or interrupted channels. New returns appear only as observations arrive. The [display configuration](data/radar_display.json)—12-second sweep, 1,000 m circle, 2.5-second return—is a visual convention, not a detection range or physical radar model. Godot uses `/api/state` to receive detection visibility and the clock atomically.

## Situation assessment and feedback priorities

The user’s agent-assessment requirement and the stakeholder mentor feedback take priority over the secondary engineering review. [Adoption status](data/references/feedback_adoption.json) records implemented, partial and deferred items. The original feedback DOCX/PDF remain local and unpublished. Three presentation cases are retained; only `case_003` is a load test. Its **240 objects are a synthetic software workload**, not a reconstruction or measurement of an attack.

**Situation assessment** evaluates a frozen received snapshot and reports known facts, uncertainty and human review items with evidence references. Request it manually, or opt into automatic assessment every 30 seconds of wall time while playback runs. The panel labels the evidence time and marks earlier snapshots. New runs suppress old results; evaluation runs in the background without blocking replay controls. Export includes the report and its bounded, allowlisted evidence bundle.

The actual Deep Agents adapter consults four tools: observations, source/fleet health, early signals and pending reviews. Input contains complete counts plus at most 12 track examples; examples are explicitly sampled. It excludes hidden positions, routes, future receipts, expired context notices, reviewer aliases and free-text reasons. Each report item must cite a supplied observation or derived-summary ID. Citation validation is not a guarantee that model prose is factually correct. No result performs an operational action or acknowledges an alert.

The default is a transparent **rule-based overview**, requiring no model or paid API. To use the real LLM adapter:

```sh
python3 -m venv .local/agent-venv
.local/agent-venv/bin/pip install -r requirements-agent.txt
# Set LOW_SKY_AGENT_MODEL=provider:model and that provider's credentials in your shell.
# OpenAI and Anthropic integrations are included; no provider or model is selected by default.
.local/agent-venv/bin/python tools/monitor_server.py
```

See [.env.example](.env.example); the server does not automatically load `.env` files. A selected model with unavailable dependencies, credentials, connection or invalid output produces an explicit failure, never a fabricated successful LLM assessment. Requests have a 20-second provider timeout, zero retries and a 60-second overall graph deadline. Actual SDK tool-calling/structured-output integration was tested with a fake chat model; **a credentialed live LLM call has not been verified in this environment**. The adapter follows the official [Deep Agents API](https://reference.langchain.com/python/deepagents/graph/create_deep_agent), using an in-memory backend and no exposed filesystem, shell or delegation tools.

## Workload, sensor fleet and durable evidence reviews

The received-track queue shows 12 rows per page with all/evidence-gap/unreviewed filters. Counts cover all received tracks. Large map views keep position symbols but show history only for the selected track; optional SIM truth remains off by default.

The [virtual fleet](data/sensor_fleet_demo.json) has **240 logical endpoints**: 60 personnel phones, 60 facility sensors, 60 civilian phones and 60 fixed phones. These are health-telemetry fixtures, independent of the A/B object-observation feeds and the two physically modeled exterior poles. At first receipt (00:01), all endpoints report online. In the load case, facility status reports arrive offline at 01:01; the fixed-phone group’s missing heartbeats become stale after 01:10. Both recover at 02:11. Loss cause remains unknown. Phone apps, audio acquisition, edge inference, sensor fusion, real agency routing and external SMS are deferred; existing open/minimized PWA current-alert notifications remain available.

Per-track explanations compute known/uncertain/missing sections from source records and health. Observation, evidence agreement, object type and intent are separate: type and intent remain unknown. **Save evidence review** requires a reviewer alias, decision and reason, and rejects an outdated evidence version. The CLI appends the received snapshot, SHA-256 evidence version, replay time and real timestamp to `.local/track-reviews.jsonl` and flushes it before confirming success. Export includes records across runs and restarts. This is local durable storage, not authenticated identity or tamper-proof storage. Existing context reviews and alert acknowledgements remain session-only.

Reproduce validation and the narrowly scoped performance measurement:

```sh
python3 -m unittest discover -s tests -q
node --test tests/*.mjs
python3 tools/benchmark_monitor.py --iterations 30
.local/agent-venv/bin/python -m unittest tests.test_situation_agent -v
```

The [recorded local benchmark](artifacts/monitor-workload-benchmark.json) measured 240 received tracks plus 240 virtual endpoints over 30 iterations: median **33.82 ms**, maximum **37.20 ms**, serialized payload **1,272,819 bytes** on Python 3.12.11/macOS. It measures state generation plus JSON serialization only; it excludes HTTP, browser/Godot rendering and LLM latency, and establishes no real-world detection accuracy.

## PWA and current-alert notifications

The monitor includes a [web app manifest](monitor/manifest.webmanifest) and [service worker](monitor/sw.js). Use **Install app** when the browser offers an installation prompt, or its install/Add to Home Screen menu otherwise. Installation availability depends on the browser. Notifications require a supported browser, HTTPS or a localhost origin, and browser/OS permission.

1. Select **Enable notifications** and allow the browser request. This sends the currently unacknowledged alerts once, including while replay is paused.
2. **Notify current alerts** manually requests the current set. Previously delivered alert IDs in the same run are suppressed.
3. While replay is playing, newly received unacknowledged alerts are batched per update. Initial loading, seeking, and starting a new run establish a baseline rather than replaying an alert backlog.
4. Selecting a notification opens **Current alerts**; it does not acknowledge anything. **Disable notifications** stops this page's delivery but does not revoke the browser's permission; change that in browser settings.

Delivery receipts in IndexedDB deduplicate the same run/alert IDs across tabs on the same origin/browser profile. Receipts older than seven days are pruned on the next delivery attempt. This is notification bookkeeping, not an audit trail. The opted-in preference is stored locally; blocked storage limits persistence.

This implementation works while the monitor is open or minimized and its polling continues. Browsers or operating systems may suspend minimized/background pages, so timely delivery is not guaranteed. There is **no server push, closed-app delivery, background polling, offline asset cache, API cache, or OSM tile cache**. The development server binds to loopback only; it is not a phone-accessible deployment. A phone requires a separate reachable HTTPS deployment. For iOS/iPadOS notification support, add the app to the Home Screen and launch it there; see [WebKit's Home Screen web-app requirements](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/). This project does not implement that article's Web Push subscription flow.

## Area early signals and fixed phones

**Area early signals** separates acoustic sensors, citizen reports, and fixed-phone observations. The [synthetic feed](data/early_warning_demo.json) shares the scenario clock but does not automatically identify tracked objects or confirm radar association. No real residents, phones, or audio are collected. Community zones A/B/C are fictional reporting areas, not surveyed neighborhoods.

| Replay time | Community event |
| --- | --- |
| 00:10 | A: acoustic candidate, single-source warning |
| 00:22 | A: delayed citizen report from 00:18, multiple sources |
| 00:28 | A: acoustic negative and citizen report conflict |
| 00:42 | A: fresh acoustic and citizen evidence agree |
| 00:45 | B: delayed report arrives |
| 01:13 | A/B evidence expires; history remains, current warning clears |
| 01:20 | B: reporting channel unavailable |

C distinguishes invalid measurements from a valid negative observation. Expiration or a negative observation does not establish safety. **Locate area** focuses the map; **Reports & sensor status** shows observation/receipt times, quality, classifier score, and evidence IDs. Scores are synthetic inputs, not attack probabilities. The 30-second freshness window, zone sizes, and events are demo assumptions. New evidence can create a new warning after an earlier one was acknowledged.

The **Exterior fixed-phone pilot** is separate from A/B/C and lies outside the fictional fence. Two 3 m poles with phone enclosures use local X/Z positions `(1000, 100)` and `(1000, 200)`, with each base grounded to the surrounding terrain. Map and Godot use the same `field_installations` entries. The display zone is centered at `(1000, 150)` with a 100 m radius; it is not sensor coverage.

- 00:00: synthetic normal power/network state and negative observation.
- 01:30: first phone candidate received; the second phone's delayed observation arrives at 01:35.
- 02:00: gateway-reported network loss and battery state, distinct from a negative observation.
- 02:30: power/network recovery and negative observations.

Cards show the **last received report's** power/network state alongside observation validity. Hardware, weatherproofing, detection performance, wiring, a phone app, audio capture, and fault diagnosis are not implemented or validated. The [civilian reference catalog](data/sensors/civilian_reference_specs.json) includes a separate `pole_phone_reference` profile.

## Sensor references

The [civilian catalog](data/sensors/civilian_reference_specs.json) records manufacturer specifications for the Infineon IM69D130 microphone and Raspberry Pi Zero 2 W. The microphone's 69 dB(A) SNR is a component characteristic under datasheet test conditions, not a detection distance. PDM conversion, drivers, and integration remain unspecified and untested; the catalog does not claim direct compatibility. Detection range, accuracy, and false-alarm rate remain `null`. Datasheet URLs, revisions, pages, and conditions are recorded.

The [picket-line review](data/references/picket_line_review.json) captures acoustic/RF/EO/thermal roles, observation versus receipt time, and communication loss versus unknown cause. RF/thermal hardware, edge inference, and actual store-and-forward are unimplemented. The source document's 20 sensors, long replay, and 60/180-second thresholds remain proposals rather than current demo settings. The local Sensor Engineering Brief and Technical Specifications informed state, timing, and uncertainty handling; original DOCX files remain unchanged and unpublished.

Radar references are not restricted to civilian products. The [counter-drone radar catalog](data/sensors/radar_reference_specs.json) cites the [Robin Radar IRIS product document](https://www.robinradar.com/hubfs/Iris%20Datasheet%20V15.7_Online.pdf), revision `RRS.IRIS.A2.2026.04`: FMCW/X-band, 360° azimuth, 60° elevation, 5/12 km instrumented range, one-second updates, and interfaces. Instrumented range, detection range, and classification range differ. The demo does not reproduce performance against any specific aircraft.

Ukraine's [ePPO app description](https://play.google.com/store/apps/details?id=ua.quick.brpg.pathfinder) describes citizen reports of observed aircraft or sounds. Installed acoustic sensors incorporating Android devices in the [US Army's overview](https://www.lineofdeparture.army.mil/Journals/Air-Defense-Artillery/ADA-Archive/2024-E-Edition/Mobility-Matters/) should not be conflated with automatic sensing on citizens' personal phones. LOW SKY keeps these input categories separate. Restart the server after editing JSON feeds; no additional packages are required.

## Detailed scenario and human review

[Situation events](data/situation_review.json) adapt indicators, delayed/conflicting reports, unknown link status, and revisiting earlier reviews from the local `LOW_SKY_Detailed_Scenario.docx`. Days and hours are compressed into a 180-second demonstration. The adaptation excludes attack sequencing, weapon selection, engagement recommendations, and unverified performance figures.

Expand **Situation & human review** to inspect received context and uncertainty, then record **noted**, **needs review**, or **dismissed** with a reason. Each record contains seven fields: event, evidence, assessment, uncertainty, decision, reason, and replay time. The 02:30 revisit links actual prior user records from the same run. Counts derive from recorded decisions; no accuracy score is calculated. Seek, reset, and case changes create a new run. Records are held in memory and disappear on server restart.

[Ukraine observation lessons](data/references/ukraine_observation_lessons.json) connect qualitative CSIS and RUSI analyses to uncertainty explanations: mixed decoys, electronic interference, and different communication links. One report does not establish aircraft role, and absent RF does not prove a fiber link. Synthetic counts, routes, and scores are not tactical models inferred from these sources.

## Airfield, terrain, and provenance

The shared layout generates seven taxiways/connectors, two aprons, eight support roads, **16 in-fence facilities**, two exterior phone poles, and five area labels in both map and Godot. Buildings include two arched hangars and generic maintenance, administration, and support structures. General airfield elements draw on [WBDG planning material](https://www.wbdg.org/ffc/dod/unified-facilities-criteria-ufc/ufc-3-260-01); the result is neither a real-base replica nor a claim of design-standard compliance. One local unit equals one meter.

The local `LOW_SKY_airfield_reference.docx` is **not fully implemented**. The current runway is 2,500 × 45 m along local north–south, rather than the proposed 2,750 m east–west layout. Hardened aircraft shelter clusters, fuel tanks/berms, a radar dome, and the northern P1–P10 picket line are absent. The arched roofs are generic hangars, not hardened shelters. Korean AIP averaging and DVIDS-based appearance studies have not been completed, so the reference document’s proposed standards-compliance README sentence is not claimed here.

The map labels the site **Fictional terrain replacement**. An opaque synthetic site replaces internal OSM roads/terrain while preserving the surrounding map. The 3D scene flattens the same polygon plus a 50 m margin and blends it into the DEM over a further 350 m. This is not a proposal to relocate roads or build an airport on that land.

[OpenStreetMap](https://www.openstreetmap.org/copyright) provides the background at the arbitrary Korean reference point. The [placement review](data/terrain/site_placement.json) compares 100 m samples: natural relief within the site bounding area decreased from approximately 367 m at the previous reference to 31 m here. The boundary is not a surveyed parcel, and road, river, flood, wind, and land-use suitability have not been comprehensively assessed. Update `monitor/map_config.json` and regenerate elevation data together when changing location. Local X points east and Z south; the small-area spherical projection is not a surveying transform.

Only visible OSM tiles are requested, with attribution and no bulk download or offline storage, following the [tile policy](https://operations.osmfoundation.org/policies/tiles/). Use `?tiles=off` for automated UI checks. The site plan and 3D work without tile networking. Google Maps/Earth content is not used.

The terrain uses bilinear interpolation of the N36E127 HGT from [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/). Source grid spacing is one arcsecond; display spacing is 50 m. Reference elevation 5 m maps to local Y=0 without vertical exaggeration. Checksums and processing provenance are in `data/terrain/`. The flattened site and transition area are synthetic; surrounding terrain retains relative DEM elevation. Satellite imagery, actual buildings, and vegetation distribution are not imported. The earlier Ukraine-inspired synthetic plains remain as a comparison preset.

External model quality and geographic accuracy are separate. Scale, pivot, and placement are adjusted for visualization:

- [Kenney City Kit Industrial](https://kenney.nl/assets/city-kit-industrial): CC0 stylized models, with provenance in `godot/third_party/kenney_industrial/provenance.json`.
- [Poly Haven](https://polyhaven.com/license): CC0 concrete, metal, asphalt, grass PBR materials, and HDRI.
- [Cesium aircraft sample](https://github.com/CesiumGS/cesium/tree/main/Apps/SampleData/models/CesiumAir): original license retained; scene scale normalized. Realistic-asset sources and hashes are in `godot/third_party/realistic/provenance.json`.

External originals remain unchanged; Godot adjusts material scale/color. Download scripts verify pinned archive SHA-256 hashes and selected files and reject unexpected upstream changes without installing packages.

The LOW SKY emblem combines brushed silver/gunmetal, angular wings, a low-altitude detection arch, and a horizon. It is fictional, not an official insignia. The [PNG](monitor/logo-metal.png) is used in the header/favicon; the [generation record](monitor/logo-metal.provenance.json) retains the image-generation prompt and method. The older [SVG](monitor/logo.svg) remains for comparison. `LOW SKY` stays HTML text for readability.

`LOW_SKY_scenario_v2.docx`, `LOW_SKY_Detailed_Scenario.docx`, and other original planning sources remain local. References in those documents to `sim/raid.py` or `core/classify.py` are not existing modules in this repository. Full source-document scenarios and engagement logic are not implemented.

## Regenerate

```sh
python3 tools/scenario_dataset.py build
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/build_assets.gd
python3 tools/fetch_asset_sample.py
python3 tools/fetch_realistic_assets.py
python3 tools/fetch_korean_terrain.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
```

## Verify

```sh
python3 -m unittest discover -s tests -v
python3 tools/scenario_dataset.py validate
python3 -m compileall -q tools tests
node --check monitor/app.js
node --check monitor/notifications.mjs
node --check monitor/sw.js
node tests/monitor_geo.mjs
node tests/monitor_radar.mjs
node tests/test_monitor_i18n.mjs
node --test tests/test_notifications.mjs
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_preview.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot --script res://tools/verify_preview.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot -- --capture
```

Run shared-clock/follow checks against a separate server to avoid changing an active user's replay:

```sh
# Test-server terminal:
python3 tools/monitor_server.py --port 8766
# Another terminal:
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_monitor.gd --quit-after 1200 -- --monitor --monitor-port=8766
```

The windowed preview check covers real GUI drag, orbit, and button interactions; headless mode skips only rendering-dependent button delivery. Capture mode requires a graphics device, saves `artifacts/korea-preview.png`, and exits. Add `--overview` for `korea-overview.png`, `--plains` for `plains-*`, or `--hills` for `asset-preview.png`/`asset-overview.png`. These checks establish asset and replay behavior, not validation of a complete agent system or real-world detection performance. Notification unit tests do not by themselves prove OS-visible delivery on every platform.
