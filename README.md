# LOW SKY — Scenario Training Workspace

[한국어](README.ko.md)

Updated demos (2026-10-11): [Korean 3-minute edition with captions](dist/demo-videos/ko/LOW_SKY_Demo_KO_Annotated.mp4) covering placement optimization, target identification, response recommendation and formation alongside the scene choices · [English 1:56 edition with captions](dist/demo-videos/en/LOW_SKY_Demo_EN_Annotated.mp4) (earlier content, unchanged). The local `dist/demo-videos/` folder also contains clean edits, SRT subtitles, chapter metadata and per-edition production notes. All recordings are silent 1080p/30fps edits of the real local UI and Godot scene; video files are local artifacts excluded from Git, with capture provenance and verification recorded alongside them.

<img src="monitor/logo-metal.png" alt="LOW SKY metallic aviation emblem" width="144" height="144">

LOW SKY combines a Godot 3D authoring view with a separate web **Decision making workspace**, synchronized to one simulation clock. The setting is a fictional airfield on a Korean map background, with a separate site plan and a photorealistic art direction. The workspace now includes overall situation assessment, received-evidence explanations and human review. Deep Agents uses OpenAI by default; the interface reports missing server credentials explicitly. An offline rule-based overview remains an explicit option.

Original planning documents remain local and are excluded from the public repository. See [MVP direction](docs/mvp-direction.md) for scope and the folders under `godot/third_party/` for asset licenses and provenance.

## Included

- [Scenario dataset](data/scenarios/v1/README.md): three 180-second cases with 48, 96, and 240 objects; 10,224 observations and 1,920 evaluation checkpoints. Only the third case is a load test.
- [Drone/source catalog](data/references/drone_sources.json): nine user-supplied names/categories and ten sources, separate from executable scenarios and not individually verified.
- [Drone scenario extension](docs/drone-scenario-extension.md): size, role, and communication concepts.
- `monitor/`: English by default, optional Korean, scenario briefings, received observations, evidence, current alerts, human review, and PWA notifications.
- `tools/monitor_server.py`: Python standard-library local server and shared clock.
- `data/site_layout.json`: a fictional 2,500 × 45 m runway, irregular 12-vertex site within a 1,200 × 2,900 m bounding box, and a 2.5 m perimeter fence. These are visualization assumptions, not a reproduced base or certified design.
- `data/terrain/korea_site.json`: public elevation data around an arbitrary northern Gyeonggi reference point, 37.90° N, 127.20° E, sampled over 10 × 10 km at 50 m spacing.
- `godot/assets/`: seven generated placeholder GLBs and asset mappings.
- `godot/third_party/kenney_industrial/`: four candidate models, textures, original license, and provenance.
- `godot/third_party/realistic/`: four PBR material sets, HDRI sky, and a Cesium aircraft sample with licenses and hashes.
- `godot/detailed_environment.gd`, `godot/plains_environment.gd`, and `godot/preview.gd`: procedural buildings, terrain presets, asset previews, and scenario replay.

## Desktop installers

The [desktop packaging guide](desktop/README.md) covers one installer containing the Tauri monitor, local Python/Deep Agents runtime, Godot 3D app, and datasets. Build macOS DMG locally on macOS and Windows NSIS locally on Windows with `desktop/build.py`. GitHub Actions installer builds are not configured. The desktop launcher starts both windows, manages their shared service, and keeps keys and journals in per-user application data. The monitor toolbar opens/activates or closes 3D and toggles fullscreen. **F6** switches workspaces; **F11** toggles fullscreen. Closing or switching 3D keeps the simulation running, and reopening reconnects to the current situation.

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

Open http://127.0.0.1:8765. The language selector stores the choice in this browser. Run a new simulation test with an optional seed; pause, resume, seek, template selection, and speed control the shared simulation. `--monitor` disables Godot's replay controls while keeping camera and terrain controls available. Godot pauses on disconnection and resynchronizes when the connection returns. The web play button does not launch Godot; open the 3D window separately.

The synchronized view starts at the overview. By default, 3D labels and screen markers appear only for fresh received detections. **Show drone positions (SIM)** is off initially; turn it on to label every simulated drone in purple, including undetected objects. Physical drone bodies continue moving in the 3D simulation. The map has its own **Show drone positions** switch, also off initially, with a separate purple truth layer and warning. These switches are independent display preferences. **Previous drone / Next drone** or **[ / ]** selects and follows any drone, wrapping at the ends. **F / Follow selected drone** toggles that selection and the overview; manual camera movement cancels follow mode. The `CAMERA / SIM` ID and index describe author-camera selection, not detection; received-only world labels remain unchanged. Selecting another template resets the camera selection. The author view provides **14 airframe variants**, including the free textured CesiumDrone (CC BY 4.0) and procedural visual approximations informed by the scenario documents. Small quads retain a provisional **0.6 m maximum horizontal span**; other airframes use separate provisional size profiles. Follow distance scales with the model. Select `visual.airframe_id` and optionally override `visual.size_profile` using `godot/assets/display_profiles.json`. See the [rendered catalog](artifacts/drone-catalog.png) and [free asset review](docs/drone-asset-review.md).

Without the server, Godot runs independently:

| Control | Action |
| --- | --- |
| 1 / 2 / 3 | Select a scenario branch |
| Space / R | Pause or resume / restart |
| Left or middle drag | Pan |
| Right or Shift + left drag | Orbit |
| Mouse wheel / left-right arrows | Zoom / rotate |
| C / H | Close-up or overview / reset camera |
| [ / ] | Select and follow previous / next drone |
| F | Follow selected drone / overview |
| T / Terrain | Korean DEM → synthetic plains → synthetic hills |

The panel’s upper-right **− / +** button collapses/expands its controls without changing playback or the camera. Buttons use explicit borders and hover, pressed, disabled and focus states. Start drags outside the control panel. `-- --plains` and `-- --hills` choose synthetic terrain presets; `-- --stylized` and `-- --blockout` select alternative assets. Terrain switching preserves the replay. The scene is an early photorealistic prototype; final environment art and aircraft replacement remain unfinished.

## Seeded simulation tests

**Run new test** creates a fresh run of the selected template and starts the shared clock. Leave **Seed** blank for a new random seed, or supply an integer from 0 to 2147483647. **Run again with same seed** regenerates the current template with the displayed seed, independent of edits in the seed field. Pause/resume, seek and **Reset current test** retain the generated input schedule. Restarting a completed test also retains its seed; use **Run new test** with a blank field for new variation. Selecting a template returns to its stopped baseline preview; opening or refreshing the page never starts a test.

The standard-library generator in [simulation_test.py](tools/simulation_test.py) copies the fixtures once at test start:

| Variable | Synthetic variation |
| --- | --- |
| Object observation delivery | 2–6% run-level probability of omitting each report; 0–3 seconds additional delay for retained reports |
| Observation-source health delivery | 0–2.5 seconds additional delay |
| Community / fixed-phone reports | 3% probability of omitting each report; 0–4 seconds additional delay |
| Virtual fleet health | Receipt delay of 0.5–2.5 seconds; existing load-case interruption boundaries vary by up to 5 seconds |

These bounds are **demo assumptions**, not measured detection performance. Object counts, 3D paths, measurement timestamps and measured positions remain fixed. A separate `visual-cast-v1` stream selects two or three existing airframe appearances and repeats each appearance in groups of six; it varies with the seed without assigning strategy, roles or performance. Its signature and object mapping are exposed only in the explicit author view as `simulation_visuals`, excluded from agent evidence. Reset and seek retain this cast; returning to a fixture restores the catalog appearances. The three template themes remain, and only `case_003` is a load test. No physical flight, acoustic propagation or radar detection model is introduced. Template descriptions contain nominal milestones, not forecasts of the generated run; timestamp columns are hidden during seeded tests. Static context notices remain separate reference inputs.

`/api/state` and `/api/clock` expose `test_run` with the seed, generator version and input SHA-256 digest, but no future generated schedule. Godot uses the same received detections and displays the seed. Agent evidence exports and confirmed decision snapshots retain this provenance; track reviews also store it. Same template + seed + generator version + unchanged fixture files reproduces received inputs at the same simulation time, including after server restart. It does **not** guarantee identical LLM prose, wall-clock checkpoint sampling or human choices. New runs invalidate old decisions. Active runs are in memory; retain the seed/digest or exported journal before restarting the server.

API: `POST /api/control` with `{"action":"start_test","case_id":"case_003","seed":42}`. Omit `seed` for randomness. Existing `play`, `pause`, `seek`, `reset`, and `case` remain compatible. Generated inputs do not modify the checked-in fixtures or their baseline evaluation expectations.

## Observations and simulation time

Godot is an **authoring view** showing simulated object movement even before detection and when observations stop. Physical drone models at their configured sizes always remain visible; only labels follow detection visibility. The count distinguishes all scene objects from detected labels. By default, the map and 3D labels show only fresh received detections. When evidence expires or its sources go offline, map markers and 3D labels disappear; the evidence list retains the last report and timestamp. Explicit negative detection rows (`detected: false`) do not reveal objects. The optional **Show drone positions** layer requests `/api/state?show_positions=1`, which returns separate `simulation_positions` at that same replay time. Truth never becomes an observation, alert, or review input; switching off or reloading hides it. Positions come from synthetic samples, normally ten seconds apart; delayed reports remain hidden until `available_at_ms`. All templates begin with no received tracks. Normal cases last 13 minutes: an indirect remote indication arrives at 00:30, while the first direct observation arrives at 04:30. Only the three-minute load case retains first reports at 00:10 and progressive appearance through 01:00. Seeded runs add delivery variation. Detection does not establish hostile intent.

Contradiction, channel loss, and stale-position alerts describe observation quality. Channels A/B are not physical RF or fiber models. Acknowledgements apply to the current run, clear on seek/reset/case change, and disappear when the server restarts. At most 1,000 acknowledgement records remain in server memory; this is not a permanent audit log.

**Scenario** and **Scenario reference & review points** explain purpose, object count, milestones, and review criteria. The cases cover first reports (48 objects), conflicting evidence and review (96), and monitoring load with channel interruption/recovery (240). Counts and routes are synthetic assumptions, not measured attack sizes. Briefings contain future events for the operator and are served separately by `/api/briefings`; received-only state and clock use `/api/state` and `/api/clock`. Area early signals use separate per-case feed overrides. The narrative concerns possible arrivals from the North Korean side toward a fictional northern Gyeonggi base. The distant departure area is schematic and not georeferenced; early reports do not establish origin, identity or intent. The authoring view begins about 18 km north in synthetic local coordinates, outside the 10 km DEM extent.

**Radar overlay** animates received observations from A/B. Scans follow the shared clock and stop for paused or interrupted channels. New returns appear only as observations arrive. The [display configuration](data/radar_display.json)—12-second sweep, 1,000 m circle, 2.5-second return—is a visual convention, not a detection range or physical radar model. Godot uses `/api/state` to receive detection visibility and the clock atomically.

## Situation assessment and feedback priorities

The user’s agent-assessment requirement and the stakeholder mentor feedback take priority over the secondary engineering review. [Adoption status](data/references/feedback_adoption.json) records implemented, partial and deferred items. The original feedback DOCX/PDF remain local and unpublished. Three presentation cases are retained; only `case_003` is a load test. Its **240 objects are a synthetic software workload**, not a reconstruction or measurement of an attack.

**Situation assessment** evaluates a frozen received snapshot and reports known facts, uncertainty and human review items with evidence references. Request it manually, or opt into automatic assessment every 30 seconds of wall time while playback runs. The panel labels the evidence time and marks earlier snapshots. New runs suppress old results; evaluation runs in the background without blocking replay controls. Export includes the report and its bounded, allowlisted evidence bundle.

The actual Deep Agents adapter consults four tools: observations, source/fleet health, early signals and pending reviews. Input contains complete counts plus at most 12 track examples; examples are explicitly sampled. It excludes hidden positions, routes, future receipts, expired context notices, reviewer aliases and free-text reasons. Each report item must cite a supplied observation or derived-summary ID. Citation validation is not a guarantee that model prose is factually correct. No result performs an operational action or acknowledges an alert.

Two providers are supported: **OpenAI** (default model `openai:gpt-6.1-sol`) and **Anthropic Claude** (recommended model `claude-opus-5`; Claude Opus 5.5, Sonnet 5, Fable 5.1 and Haiku 4.5 are also listed, and any other model ID can be typed). Both run through the same Deep Agents graph, evidence tools, structured report schema and citation validation.

### Choosing a model and entering your own API key

Select **AI settings** in the header (desktop: **LOW SKY → AI model & API key…**). Choose OpenAI, Anthropic Claude or the offline rules-only overview, pick a model, paste your API key, select **Test connection**, then **Save**. New assessments use the saved setting immediately; no restart is needed. Each user brings their own key, and usage is billed to that user's provider account.

- **Storage:** the key is saved only on that computer, in `agent-settings.json` with owner-only permissions. The desktop app keeps it in the per-user application data folder; a source checkout uses `.local/agent-settings.json` (`--agent-settings-path` overrides it). Keys for OpenAI and Anthropic are kept separately, so switching providers does not lose either key.
- **Exposure:** the settings API is write-only for keys. Responses show only whether a key exists, where it came from and its last four characters. The key is passed directly to the model client for each request and is never placed in the process environment, logs, assessment exports or the Codex operator subprocess. The local service accepts settings changes only from its own loopback page.
- **Connection test:** **Test connection** asks the provider to look up the selected model with the entered key, through the official OpenAI and Anthropic SDKs. It generates no tokens and reports invalid keys, missing model access, rate limits and network failures separately.
- **Fallback:** without a saved setting, the earlier `.env` and environment variables still work: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, optional `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL`, and `LOW_SKY_AGENT_MODEL` (`openai:<model>`, `anthropic:<model>`, or empty for rules only). A key saved in the dialog takes priority over the environment.

```sh
python3 -m venv .local/agent-venv
.local/agent-venv/bin/pip install -r requirements-agent.txt
.local/agent-venv/bin/python tools/monitor_server.py
# Open http://127.0.0.1:8765 → AI settings, or set keys in .env as before.
```

**Claude specifics.** Claude models that support it run with adaptive thinking. LangChain normally forces a structured-output tool call, which Claude rejects while thinking is on (Opus 5.5 and Fable 5.1 reject forced tool calls entirely). The adapter therefore declares adaptive thinking explicitly so `langchain-anthropic` relaxes the choice to automatic, and the system prompt requires the final report tool call. A run that ends without that call fails validation instead of producing a result. Claude requests allow up to 16,000 output tokens, a 120-second per-request timeout, zero retries and a 300-second overall deadline; OpenAI keeps 60 and 180 seconds.

Keep keys out of chat and browser storage. `.env` and `.local/` are ignored by Git; only the key-free `.env.example` is tracked. The `.env` loader supports single-line `KEY=value`, optional `export`, quotes and comments, with no variable or command expansion, and needs a restart. Key presence is only a configuration check; use **Test connection** to confirm access. A selected model with unavailable dependencies, credentials, connection or invalid output produces an explicit failure, never a fabricated successful LLM assessment. SDK tool calling and structured output are tested offline with local fixtures for both providers, including a full Claude tool loop through the real `langchain-anthropic` client against a loopback Messages endpoint. A credentialed **GPT-6.1 Sol** assessment of the synthetic 240-track case was verified in the browser on 2026-10-10. No credentialed Claude run has been recorded in this repository. These are integration checks, not model-quality comparisons. The adapter follows the official [Deep Agents API](https://reference.langchain.com/python/deepagents/graph/create_deep_agent), using an in-memory backend and no exposed filesystem, shell or delegation tools.

## Event-driven decision checkpoints

**Assess important events while running** is enabled by default. Each checkpoint uses the entire frozen received snapshot, with a concise overall situation summary and the main uncertainty above three choices. Full findings and evidence references remain expandable; the confirmation dialog repeats the summary and selected effect. Important received changes produce a captured-evidence card while the shared monitor/Godot clock keeps advancing, including during model calls and user selection. The three standard manual review choices appear immediately, even while the agent is queued, evaluating or unavailable. They are explicitly labeled as standard choices, with no invented agent recommendation. A validated agent report replaces the standard explanation when it arrives; the agent cannot confirm a choice. A persistent **View choices** notice also reports missed decisions.

Triggers are first received tracks, the onset/clearance of conflicting or stale tracks, observation-source loss/recovery, virtual-fleet loss/recovery, and area early-signal changes. Repeated heartbeats and changing IDs alone do not interrupt. Changes are grouped by source/area or aggregate condition, not one prompt per object. Seek/reset establishes a new baseline; **Request a decision checkpoint** evaluates the current received situation explicitly. Disabling guided replay leaves normal playback available. The separate 30-second automatic overview is disabled while guided replay is on.

| Human choice | Confirmed local effect |
| --- | --- |
| Continue monitoring | Record continued monitoring; leave playback unchanged. |
| Request evidence review | Record additional evidence review; leave playback unchanged. |
| Defer for further review | Record an unresolved follow-up; leave playback unchanged. |

Select an option, then **Confirm and apply**; comments and aliases remain optional. Decisions never pause, rewind, resume or restart the simulation, including at scenario end. Only explicit playback controls change playback. A failed model call leaves playback unchanged and keeps the standard manual choices usable until expiry. These choices are not a model assessment. The Codex operator still waits for a validated assessment; it cannot silently use standard choices as an agent result.

Cards expire when their relevant situation changes materially, at the case-specific deadline, or at scenario end. Normal cases allow **120 simulation seconds for indirect-indication review** and **90 seconds after direct observations**; the compact load case retains 30 seconds. These are training assumptions, not operational response standards. First direct observation closes obsolete pre-detection choices. Routine new receipts do not alone invalidate a choice: the card marks new evidence and confirmation records both captured and current received evidence. Unrelated area changes do not expire a targeted card. The clock continues during model calls and confirmation; optional 0.5× speed provides more reading time. The UI closes expired choices and explains why. The server rejects late submissions and results. Reset, seek and new runs supersede prior cards. Records include the actual decision simulation time separately from evidence time.

Confirmed decisions are flushed to `.local/event-decisions.jsonl` before applying their local effect, including the event, received evidence bundle, exact report, evidence version, reviewer alias, reason and timestamp. **Export decision journal** / `/api/decisions/audit` exports all runs; the panel history shows the current run. This is a local journal, not authenticated identity or tamper-proof remote storage. Unconfirmed event cards are in memory (last 100); restarting the server clears them. The CLI accepts `--decision-audit-path` for isolated tests.

For a seeded shared-clock integration check, start an isolated rules server, then run:

```sh
LOW_SKY_AGENT_MODEL='' .local/agent-venv/bin/python tools/monitor_server.py --port 8766 --audit-path .local/test-track-reviews.jsonl --decision-audit-path .local/test-decisions.jsonl
# In another terminal:
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_decisions.gd --quit-after 1200 -- --monitor --monitor-port=8766
```

The credentialed Sol integration was verified on an `case_003` source-loss event in the earlier pause-based version: all required evidence tools were consulted, three cited choices passed validation, and the UI required explicit confirmation. This verifies software behavior in the synthetic scenario, not real-world decision quality.

## Notification priority

Low-priority repeated reports stay in the event list. Meaningful area/source changes are deduplicated and grouped into one top-center toast. First direct observations with an available review, even without prior indirect indications, or expiry of a choice the user was selecting, opens a central acknowledgement dialog. These levels describe review urgency, not real threat severity. Dialogs never pause time or confirm decisions; an existing dialog or text entry defers interruptions. Stale and previous-run notices are discarded. Opt-in PWA notifications use the same filtering; they require the app to remain open or minimized.

## Scene choices

Use the expanded **Scene choices** panel at the top of **Decisions** to choose and confirm a predetermined scene outcome for a currently observed aircraft. Normal cases include two fixed vignettes: an impact-style final approach (11:15–11:30, `object_11`) and an abstract payload drop/retreat (11:45–12:00, `object_12`). With no branch, each scene completes and its fixed facility becomes unavailable. The hold/return choices produce partial/prevented outcomes after five simulation seconds; continuing preserves the authored finale. Godot shows motion, a dropped object, impact flash, debris, fire, smoke and charred facility surfaces. Effects follow the shared clock and clear on rewind/reset; partial and prevented outcomes have separate status labels without damage effects. The map marks the selected facility immediately, then shows its published status. Facility inventory remains expandable. Godot panel text is 1.5× larger, with wrapped labels and scrollable controls. Choices after completion are rejected. Other objects retain the existing five-second scene branches. These are visual story events, not physical weapon or defense models.

The clock continues during selection and execution. One branch is allowed per run; seek, reset, case change, new run or server restart clears it. Branch selection is session-only, distinct from the durable review-decision journal. The situation agent receives the selected branch and facility status as a labeled exercise summary without hidden coordinates. These are explicit scene-authoring outcomes, not modeled interception, weapon damage, or measured defensive effectiveness. All facilities begin available as a scenario assumption.

## Optional Codex virtual test operator

Start a **Run new test**, then expand the compact **Codex virtual test operator** tool at the bottom of the workspace and use **Start automatic test decisions** when you want Codex to act as a simulated reviewer. It is off by default and applies only to the current seeded test. The normal situation-assessment agent still produces the evidence and choices; a separate actual Codex CLI call chooses one, explains why, and the server validates and records it before applying its local effect. **Stop and take over** cancels an in-flight answer without changing playback.

This requires an installed, authenticated `codex` CLI (`codex login status`). Its authentication is separate from the situation agent's project `.env` API key; that key is not passed to the subprocess. The adapter uses `gpt-6.1-sol` with medium reasoning, an ephemeral temporary directory, read-only sandbox, strict output schema, and disabled shell/browser/delegation tools. It follows [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive). Codex usage applies. Missing CLI/authentication, timeout or invalid output stops automation explicitly; there is no rules fallback for automatic choices. The subprocess adapter currently targets POSIX/macOS/Linux.

The default limit is 3 decisions, adjustable from 1 to 10. A hold choice, decision limit, 10-minute session deadline, assessment/selection failure or manual override ends automation; each Codex call has a 120-second deadline. Pause, seek, reset, case changes and new tests cancel pending choices. New tests can start normally after cancellation; automatic decisions must be enabled again. Speed changes alone do not cancel it.

Automatic records carry `actor.type=automated_test`, provider, model and operator-session ID, and appear as **AUTOMATED TEST** in the UI and exported journal. They are never presented as human approvals. Codex receives only the displayed received-evidence report and the three local choices; hidden positions and future inputs are excluded. An evidence-review choice stops automation without stopping playback. Expired choices are never applied. Seed reproducibility covers generated inputs, not identical model decisions. The HTTP interface is `GET/POST /api/test-operator`; start requires `action: "start"`, the current `run_id`, `confirm: true` and optional `max_decisions`.

The earlier seed-42 integration verified the actual Codex CLI and automated journaling. Its former pause-on-hold behavior has been replaced: automated selections now share the same expiry checks and never change playback. Current regression tests and the isolated Godot integration verify continuous playback; these checks do not require provider calls.

## Target identification, response recommendation, formation and placement optimization

The **Decisions** pane now carries a rule-based **training recommendation layer** (`tools/tactics.py`, catalog in [data/tactics/catalog.json](data/tactics/catalog.json)). It turns the local scenario documents' decoy-vs-attack rubric, effector allocation table, penalize-versus-reject constraint engine, counter-drone team pre-positioning and P1–P10 picket line into explicit, bilingual advice over **received evidence only**. Nothing in this layer changes aircraft motion, observations or facility status; confirming a recommendation records a human decision and simulates no interception, damage or detection performance. Scores are uncalibrated rubric points from the documents, shown as a lean with cues and uncertainty items rather than percentages.

- **Target identification** (`state.tactics.targets[].identification`) derives speed, altitude, heading persistence, descent, group structure and the nearest facility from each received track's observation history, and merges arrived reports from a new synthetic classifier feed ([data/tactics/identification_demo.json](data/tactics/identification_demo.json): EO airframe class with payload not visible, acoustic jet/propeller signatures, RF emission or its absence). The result is a lean among decoy-leaning, attack-leaning, reconnaissance-leaning, indeterminate or insufficient data, a profile (jet, multirotor, fixed wing, light airframe, unclassified), a verification level that never exceeds *observed class*, the cue list with evidence IDs, and uncertainty items such as *payload not visible*, *EO reports conflict* or *absent RF is not proof of a fiber link*. The feed is built offline by `tools/build_identification_feed.py` from fixture appearance with deliberate omissions, delays and conflicts; the server never reads world truth for identification and seeded runs do not vary it.
- **Weapon recommendation** (`response`) lists four effectors from the catalog — interceptor drone, laser, autocannon, RF jammer — each as *recommended*, *penalized* or *rejected* with reasons. Rejections: every effector while the aircraft is over the runway corridor; autocannon when debris would fall inside the fence or near fuel-like facilities; jammer within 1,500 m of the tower or stations, or after a negative RF report; interceptor when the 12-per-run inventory is spent. Penalties: interceptor against jet-speed targets and decoy-leaning groups (resource preservation), jammer without RF evidence, laser while another laser allocation is active, and any effector with no placed effector team in nominal range. The posture is *observe and preserve*, *hold* or *engage candidate*; **Record allocation** opens a confirm dialog with optional alias and comment, validates the card version and run, and appends to `.local/tactics-decisions.jsonl` (`--tactics-audit-path`, export at `/api/tactics/audit`). One allocation per aircraft per run; reset, seek and new runs start fresh while the journal is kept.
- **Force & sensor placement** completes the earlier personnel scaffold with four unit kinds and budgets: 12 infantry, 2 military radars, 10 detection-phone posts and 4 effector teams. A deterministic greedy coverage heuristic over the site layout, the DEM and mapped OSM road centerlines proposes positions: radars on elevated fence-ring sites facing the heaviest sectors, phone posts on exterior road sides outside the fence (existing power and access as a proxy), effector teams on the fence ring outside the runway corridor, observation posts at remaining gaps, a quick-reaction group near the apron and an east-road patrol. The first proposal uses the documents' north-biased scenario prior; **Re-optimize from current picture** re-weights sectors from received tracks and positive area signals. **Apply proposal** places all units; **Choose manually** enables click placement, moving and removal per kind within budgets and ±5 km. Range rings on the site plan and in 3D are display assumptions, not propagation or detection modeling. Units reset with the run.
- **Tactical formation** (`formation`) groups placed units into sector teams with roles (surveillance, picket, response, observation post, quick reaction, patrol) and lists the identified aircraft each sector currently faces, with an overall posture of ready, observe, respond or hold.

Godot renders the four unit kinds with their rings and appends the lean, profile and any recorded allocation to detected drone labels; author-view labels are unchanged. The situation agent receives only counts (placed units by kind, allocations, targets by lean, postures) labeled as rule-based training advice; its instructions still forbid inventing weapon selection. See [the design note](docs/superpowers/specs/2026-10-11-tactics-layer-design.md) for assumptions.

## Decision rehearsal review

Expand **Decision rehearsal review** below the decision panel to inspect saved runs by scenario and seed. Human and automated decisions are counted separately, alongside continue/hold/defer choices. Each record shows its original assessment and uncertainty. **Export seven-field records** downloads the selected run's event, received evidence, assessment, uncertainty, decision, optional comment and timestamps, with evidence provenance retained. Refresh after more decisions or a new run. The UI lists up to 50 runs and displays the latest 100 decisions; selected-run export includes every decision in that run. This is a read-only view of the durable journal, not an accuracy score or automatic model-training loop.

**Show choices in English and Korean** displays both languages for choice labels and effects. Model reasoning remains in its original assessment language; toggling bilingual labels does not make a model call or change a decision.

`GET /api/rehearsals` returns run summaries; `GET /api/rehearsals?run_id=...` exports the selected run. The internal suggestion document's adoption and remaining gaps are recorded in [Suggestion adoption](docs/suggestion-adoption.md), including the actual three-scenario scope and the absence of verified SAPIENT, single-file site switching or VR support. The source document stays local.

## Workload, sensor fleet and durable evidence reviews

Received events sit directly below the map controls, independently of the evidence column height. Long observation evidence scrolls within its own panel; switching to Current alerts retains the event log.

The received-track queue shows 12 rows per page with all/evidence-gap/unreviewed filters. Counts cover all received tracks. Large map views keep position symbols but show history only for the selected track; optional SIM truth remains off by default.

The [virtual fleet](data/sensor_fleet_demo.json) has **240 logical endpoints**: 60 personnel phones, 60 facility sensors, 60 civilian phones and 60 fixed phones. These are health-telemetry fixtures, independent of the A/B object-observation feeds and the two physically modeled exterior poles. At first receipt (00:01), all endpoints report online. In the load case, facility status reports arrive offline at 01:01; the fixed-phone group’s missing heartbeats become stale after 01:10. Both recover at 02:11. Loss cause remains unknown. Phone apps, audio acquisition, edge inference, sensor fusion, real agency routing and external SMS are deferred; existing open/minimized PWA current-alert notifications remain available.

Per-track explanations compute known/uncertain/missing sections from source records and health. Observation, evidence agreement, object type and intent are separate: type and intent remain unknown. **Save evidence review** requires a review decision and rejects an outdated evidence version. Optional comment buttons offer wording based on received evidence gaps, source disagreement or stale reports. Click a suggestion to select it, click again to clear it, then save; suggestions never save automatically. Free text and reviewer alias are optional, inside a disclosure. The CLI appends the received snapshot, SHA-256 evidence version, replay time and real timestamp to `.local/track-reviews.jsonl` and flushes it before confirming success. Export includes records across runs and restarts. This is local durable storage, not authenticated identity or tamper-proof storage. Existing context reviews and alert acknowledgements remain session-only.

Reproduce validation and the narrowly scoped performance measurement:

```sh
python3 -m unittest discover -s tests -q
node --test tests/*.mjs
python3 tools/benchmark_monitor.py --iterations 30
.local/agent-venv/bin/python -m unittest tests.test_situation_agent -v
```

The [recorded local benchmark](artifacts/monitor-workload-benchmark.json) measured 240 received tracks plus 240 virtual endpoints over 30 iterations: median **58.04 ms**, maximum **65.75 ms**, serialized payload **1,990,963 bytes** on Python 3.12.11/macOS (re-measured on 2026-10-11 with the tactics layer; the earlier observation-only run measured 33.82 ms and 1,272,819 bytes). It measures state generation plus JSON serialization only; it excludes HTTP, browser/Godot rendering and LLM latency, and establishes no real-world detection accuracy.

## PWA and current-alert notifications

**Alert sound** is independent of notification permission. Use the sound button beside the view tabs to mute or enable it; the preference is saved locally. Sound activates after an interaction with the page: low urgency uses one soft tone, medium uses two notes, and high uses three warning pulses. The highest level in each batch wins; semantic deduplication and real-time cooldowns (30/8/3 seconds) suppress repeated sounds. Initial load, seeks, reconnection catch-up and paused playback stay silent. System notifications request silent delivery to avoid a second chime. Background suspension or system audio settings may prevent sound.

The monitor includes a [web app manifest](monitor/manifest.webmanifest) and [service worker](monitor/sw.js). Use **Install app** when the browser offers an installation prompt, or its install/Add to Home Screen menu otherwise. Installation availability depends on the browser. Notifications require a supported browser, HTTPS or a localhost origin, and browser/OS permission.

1. Select **Enable notifications** and allow the browser request. This sends the currently unacknowledged alerts once, including while replay is paused.
2. **Notify current alerts** manually requests the current set. Previously delivered alert IDs in the same run are suppressed.
3. While replay is playing, newly received unacknowledged alerts are batched per update. Initial loading, seeking, and starting a new run establish a baseline rather than replaying an alert backlog.
4. Selecting a notification opens **Current alerts**; it does not acknowledge anything. **Disable notifications** stops this page's delivery but does not revoke the browser's permission; change that in browser settings.

Delivery receipts in IndexedDB deduplicate the same run/alert IDs across tabs on the same origin/browser profile. Receipts older than seven days are pruned on the next delivery attempt. This is notification bookkeeping, not an audit trail. The opted-in preference is stored locally; blocked storage limits persistence.

This implementation works while the monitor is open or minimized and its polling continues. Browsers or operating systems may suspend minimized/background pages, so timely delivery is not guaranteed. There is **no server push, closed-app delivery, background polling, offline asset cache, API cache, or OSM tile cache**. The development server binds to loopback only; it is not a phone-accessible deployment. A phone requires a separate reachable HTTPS deployment. For iOS/iPadOS notification support, add the app to the Home Screen and launch it there; see [WebKit's Home Screen web-app requirements](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/). This project does not implement that article's Web Push subscription flow.

## Area early signals and fixed phones

**Area early signals** separates acoustic sensors, citizen reports, and fixed-phone observations. The [synthetic feed](data/early_warning_demo.json) shares the scenario clock but does not automatically identify tracked objects or confirm radar association. No real residents, phones, or audio are collected. Community zones A/B/C are fictional reporting areas, not surveyed neighborhoods. Normal cases add a schematic remote area: first indication at 00:30, same-source renewals, delayed reports, a second report and conflicting evidence before direct observations at 04:30. The table below describes only the compact load-case feed.

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

[Situation events](data/situation_review.json) adapt indicators, delayed/conflicting reports, unknown link status, and revisiting earlier reviews from the local `LOW_SKY_Detailed_Scenario.docx`. Days and hours are compressed into a 180-second demonstration. The adaptation excludes attack sequencing and unverified performance figures; weapon selection and engagement recommendations exist only as the separate rule-based training layer described above, which records human decisions without simulating engagements.

Expand **Situation & human review** to inspect received context and uncertainty, then record **noted**, **needs review**, or **dismissed** with an optional suggested comment or free text. Each record contains seven fields: event, evidence, assessment, uncertainty, decision, reason, and replay time. The 02:30 revisit links actual prior user records from the same run. Counts derive from recorded decisions; no accuracy score is calculated. Seek, reset, and case changes create a new run. Records are held in memory and disappear on server restart.

[Ukraine observation lessons](data/references/ukraine_observation_lessons.json) connect qualitative CSIS and RUSI analyses to uncertainty explanations: mixed decoys, electronic interference, and different communication links. One report does not establish aircraft role, and absent RF does not prove a fiber link. Synthetic counts, routes, and scores are not tactical models inferred from these sources.

## Airfield, terrain, and provenance

The shared layout generates seven taxiways/connectors, two aprons, eight support roads, **16 in-fence facilities**, two exterior phone poles, and five area labels in both map and Godot. Buildings include two arched hangars and generic maintenance, administration, and support structures. General airfield elements draw on [WBDG planning material](https://www.wbdg.org/ffc/dod/unified-facilities-criteria-ufc/ufc-3-260-01); the result is neither a real-base replica nor a claim of design-standard compliance. One local unit equals one meter.

The local `LOW_SKY_airfield_reference.docx` is **not fully implemented**. The current runway is 2,500 × 45 m along local north–south, rather than the proposed 2,750 m east–west layout. Hardened aircraft shelter clusters, fuel tanks/berms, a radar dome, and the northern P1–P10 picket line are absent. The arched roofs are generic hangars, not hardened shelters. Korean AIP averaging and DVIDS-based appearance studies have not been completed, so the reference document’s proposed standards-compliance README sentence is not claimed here.

The map labels the site **Fictional terrain replacement**. An opaque synthetic site replaces internal OSM roads/terrain while preserving the surrounding map. The 3D scene flattens the same polygon plus a 50 m margin and blends it into the DEM over a further 350 m. This is not a proposal to relocate roads or build an airport on that land.

[OpenStreetMap](https://www.openstreetmap.org/copyright) provides the background at **37.90° N, 127.20° E**, an arbitrary northern Gyeonggi visual reference. This is not an actual airbase, surveyed parcel or approved construction site. The [placement record](data/terrain/site_placement.json) identifies the synthetic terrain replacement and unassessed land-use constraints. Update `monitor/map_config.json` and regenerate elevation data together when changing location. Local X points east and Z south; the small-area spherical projection is not a surveying transform. Remote indication regions appear only on the schematic site plan, not as claimed real border locations.

Only visible OSM tiles are requested, with attribution and no bulk download or offline storage, following the [tile policy](https://operations.osmfoundation.org/policies/tiles/). Use `?tiles=off` for automated UI checks. The site plan and 3D work without tile networking. Google Maps/Earth content is not used.

The terrain uses bilinear interpolation of the N37E127 HGT from [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/). Source grid spacing is one arcsecond; display spacing is 50 m. Reference elevation 105 m maps to local Y=0 without vertical exaggeration. Checksums and processing provenance are in `data/terrain/`. The flattened site and transition area are synthetic; surrounding terrain retains relative DEM elevation. The same extent uses a 2021 Sentinel-2 composite, ESA WorldCover-guided forest instances, and OSM road centerlines/building footprints. Heights and individual trees are approximate, and OSM coverage is incomplete; see [surroundings, provenance and limitations](docs/korean-surroundings.md) and [asset licenses](godot/assets/terrain/ATTRIBUTION.md). Moving aircraft and their labels receive a uniform 642 m display-only height offset in geographic mode so the illustrative flight paths remain visible over the mountainous background. Authored coordinates, observations, ground assets and map positions are unchanged; this is not terrain-following flight. Terrain beyond the 10 km DEM remains schematic. The earlier Ukraine-inspired synthetic plains remain as a comparison preset.

External model quality and geographic accuracy are separate. Scale, pivot, and placement are adjusted for visualization:

- [Kenney City Kit Industrial](https://kenney.nl/assets/city-kit-industrial): CC0 stylized models, with provenance in `godot/third_party/kenney_industrial/provenance.json`.
- [Poly Haven](https://polyhaven.com/license): CC0 concrete, metal, asphalt, grass PBR materials, and HDRI.
- [Cesium aircraft sample](https://github.com/CesiumGS/cesium/tree/main/Apps/SampleData/models/CesiumAir): original license retained; scene scale normalized. Realistic-asset sources and hashes are in `godot/third_party/realistic/provenance.json`.

External originals remain unchanged; Godot adjusts material scale/color. Download scripts verify pinned archive SHA-256 hashes and selected files and reject unexpected upstream changes without installing packages.

The LOW SKY emblem combines brushed silver/gunmetal, angular wings, a low-altitude detection arch, and a horizon. It is fictional, not an official insignia. The [PNG](monitor/logo-metal.png) is used in the header/favicon; the [generation record](monitor/logo-metal.provenance.json) retains the image-generation prompt and method. The older [SVG](monitor/logo.svg) remains for comparison. `LOW SKY` stays HTML text for readability.

`LOW_SKY_scenario_v2.docx`, `LOW_SKY_Detailed_Scenario.docx`, and other original planning sources remain local. References in those documents to `sim/raid.py` or `core/classify.py` are not existing modules in this repository. Full source-document scenarios are not implemented; the documents' classification rubric, allocation table and constraint engine are adapted as the rule-based training recommendation layer (no engagement simulation).

## Regenerate

```sh
python3 tools/scenario_dataset.py build
python3 tools/build_early_warning.py
python3 tools/build_identification_feed.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/build_assets.gd
python3 tools/fetch_asset_sample.py
python3 tools/fetch_realistic_assets.py
python3 tools/fetch_korean_terrain.py
python3 tools/fetch_korean_context.py
python3 tools/build_korean_context.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
```

## Verify

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_tactics -v
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
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_units.gd
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

## Judgment dashboard

Scenario selection, description, and expandable reference timeline share the top section beside the simulation controls. On desktop (at least 1100px wide and 700px tall), the map and received events stay visible while the adjacent inspector scrolls independently. Switch between **Decisions**, **Evidence**, **Signals**, and **Tools & records**; on narrower screens, **Map** is another panel. Pending decision and signal counts remain on the panel buttons. Panel changes do not pause the simulation. Scenario references expand independently of the compact playback controls. Selection menus use the workspace’s own dropdowns, with keyboard navigation and Escape to cancel.


The **Decision dashboard** in the **Decisions** panel summarizes received evidence, remaining review time, available review actions, the cost of waiting, and the local decision maker for the selected object. Actions use explicit confirmation; comments are optional and dismissal requires a suggested reason. The simulation keeps moving while a confirmation is open, and changed or expired choices cannot be applied.

**Continue observing** or **Request sensor review** schedules a clearly labeled, predetermined visual-review receipt after 30 simulation seconds. The 90-second per-object review window continues counting down. These are review deadlines and scripted receipts, not target arrival estimates or real EO measurements. Follow-up arrival also triggers the existing situation agent. The seven-field dashboard journal exports at `/api/dashboard/audit` and persists to `.local/dashboard-decisions.jsonl`; restart/reset starts a fresh active run without deleting saved records. See [decision dashboard adoption](docs/decision-dashboard-adoption.md) for state semantics, limitations, and the proposal mapping.

High-priority audio uses three stronger triangle-wave pulses with a short sustain and bounded gain; browser user activation and the mute control still apply. Repeated events remain deduplicated. Actual volume depends on system and speaker settings.
