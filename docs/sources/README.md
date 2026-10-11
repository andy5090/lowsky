# Source documents / 원본 기획 문서

The original planning documents live in this folder **on team members' computers only**. They are internal (team proposals, Air Force mentor feedback) and this repository is public, so `.gitignore` keeps every file here out of Git except this index. Ask the team for copies and place them in the subfolders below with the same file names.

이 폴더의 원본 기획 문서는 **팀원 각자의 컴퓨터에만** 둔다. 팀 내부 제안과 공군 멘토 피드백이 포함되어 있고 저장소는 공개 상태이므로, `.gitignore`가 이 색인을 제외한 모든 파일을 Git에서 제외한다. 사본은 팀에 요청해 아래 하위 폴더에 같은 파일명으로 둔다.

| Folder | File | Contents | Where it was adopted |
| --- | --- | --- | --- |
| `planning/` | `LOW_SKY_team_brief.docx` | Team brief: explainable decision support for defending an airfield against cheap drones | [MVP direction](../mvp-direction.md) |
| `planning/` | `LOW_SKY_scenario_v2.docx` | Scenario v2 "first night": precursor signals, decoy discrimination rubric, effector table, simulator parameters | [Drone scenario extension](../drone-scenario-extension.md), [tactics layer](../superpowers/specs/2026-10-11-tactics-layer-design.md), `godot/assets/display_profiles.json` |
| `planning/` | `LOW_SKY_Detailed_Scenario.docx` | "02:00" intelligence-officer narrative across the 72 hours before first contact | `data/situation_review.json`, `data/scenarios/v1/briefings.json`, [tactics layer](../superpowers/specs/2026-10-11-tactics-layer-design.md) |
| `planning/` | `LOW_SKY_picket_line.docx` | National low-altitude picket line: distributed low-cost acoustic/RF/EO sensors | `data/references/picket_line_review.json`, detection-phone placement |
| `planning/` | `LOW_SKY_airfield_reference.docx` | Public references for a Korean-looking fictional airbase (UFC 3-260-01, eAIP, DVIDS) | README "Airfield, terrain, and provenance" (partially implemented) |
| `planning/` | `LOW_SKY_Suggestion.docx` | One-minute expansion pitch: vendor-neutral decision layer and rehearsal | [Suggestion adoption](../suggestion-adoption.md) |
| `planning/` | `LOW_SKY_decisiondashboard.docx` | Decision-dashboard action scenarios for the commander | [Decision dashboard adoption](../decision-dashboard-adoption.md) |
| `engineering/` | `LOW_SKY_Sensor_Engineering_Brief.docx` | Sensor data engineering brief for synthetic observations | Observation/receipt timing and uncertainty handling |
| `engineering/` | `LOW_SKY_Sensor_Technical_Specifications.docx` | Sensor technical specification sheet (synthetic-data MVP) | `data/sensors/` reference catalogs |
| `feedback/` | `LOW_SKY_멘토피드백.docx` | Air Force mentor feedback (mass-attack problem first) | `data/references/feedback_adoption.json` |
| `feedback/` | `LOW_SKY_Detailed_Feedback_Issues_and_Solutions.pdf` | Detailed engineering review: issues and proposed solutions | `data/references/feedback_adoption.json` |
| `evidence/` | `LOW_SKY_Verified_Source_Evidence_Dossier.pdf` | Verified public-source evidence dossier | `data/references/` source registers |

Code, data and docs refer to these documents by file name only. No build, test or runtime step reads them, and the desktop installer never includes them.

코드·데이터·문서는 파일명으로만 참조한다. 빌드·테스트·실행 단계에서 이 파일들을 읽지 않으며 데스크톱 설치 파일에도 포함되지 않는다.
