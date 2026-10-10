# Suggestion adoption

The internal `LOW_SKY_Suggestion.docx` proposes a pitch expansion around a vendor-neutral decision layer and repeated decision rehearsal. This update implements received-evidence review capabilities in the existing simulation. It does not introduce weapons allocation, engagement recommendations, live sensor control or automatic policy learning.

## Implemented

| Proposal | Current implementation | Boundary |
| --- | --- | --- |
| Rehearsal → decision records → review | The Decision rehearsal review panel groups durable decisions by run and input seed, separates human and automated actors, and shows the selected local review effects. | Counts describe workflow activity, not accuracy, proficiency or effectiveness. Reviewing records does not retrain an agent or modify delegation rules. |
| Seven-field records | Selected-run JSON export contains event, received evidence, assessment, uncertainty, decision, optional reason and time; record IDs, evidence version and original snapshot hash remain attached. | Derived review export, not a combat dataset or a certified interoperable schema. The original decision journal remains the source of record. |
| English/Korean cards | Optional simultaneous English/Korean choice labels and local effects. | Agent reasoning and archived reports retain their original language. Full bilingual model reports are not implemented. |
| Repeatable rehearsal | Existing seeded input variation, shared Godot clock, selectable drone cameras and opt-in Codex virtual operator remain available. | Input reproducibility does not guarantee identical LLM decisions; there is no VR implementation. |
| Sensor-independent decision layer | Existing observed-input schemas, evidence bundles and source identifiers remain separate from the 3D authoring view and model choice. | No live third-party sensor integration or SAPIENT compatibility is claimed. |

## Claims requiring separate work

- **Scenario count:** the repository has three active scenarios (12, 24 and 240 objects), with exactly one monitoring load case. The proposal's “12 cases” does not describe this version. The earlier instruction to keep a few focused scenarios takes precedence.
- **SAPIENT:** a versioned adapter, official schema validation, timestamp/coordinate mapping and interoperability testing are required before making a compatibility claim. Current JSON alone is not proof.
- **Site replacement:** layout, terrain, georeferencing, asset geometry and source positions are currently coordinated across several files. A one-file YAML site switch is not implemented; replacing metadata alone would misalign the map and 3D view.
- **Constraints and delegation:** the current server validates run identity, captured-situation validity, response deadlines, supported review choices and durable recording; choices leave playback unchanged. It does not evaluate weapon suitability, allocate effectors or learn authority thresholds from rehearsal records.
- **Infrastructure and rollout:** IoT eSIM nodes, external institutional routing, deployment at a real airfield, VR and the proposed 12/36-month commercial rollout remain proposals. Existing PWA notifications work while open/minimized.
- **Market and cost claims:** dates, geopolitical events, unique-market assertions, node prices, national coverage costs, interceptor comparisons and exercise frequency in the pitch require independent primary-source verification before publication. They were not copied into product claims or simulation parameters.

## Minimal-input evidence review

Track and context reviews now offer optional suggested comments. Track suggestions depend on received disagreement, stale reports and missing evidence; they never assert identity or intent. Nothing is preselected. The user chooses a review decision, optionally selects a comment, and saves. Free text and reviewer aliases are optional. A selected track comment pins its evidence version so newer evidence still requires an explicit refresh.

## Review workflow

1. Run a scenario and confirm a local decision, with or without an additional comment. The optional Codex operator records its choices as automated decisions.
2. Expand **Decision rehearsal review**, select a recorded run and inspect its saved choices and uncertainties. Refresh explicitly after more decisions or a new run.
3. Export that run's seven-field records for review. The UI lists the current run plus the most recent recorded runs (up to 50), and displays the latest 100 decisions for a selected run. Its export includes all decisions in that run. Existing full-journal export includes all runs.

The view is read-only. It cannot resume an old run, replay an old confirmation, change policy, send messages or start model calls. Empty current runs can be inspected; older runs without any confirmed decision have no durable decision record. Historical input provenance may be unavailable for decisions recorded before seeded simulations were introduced.
