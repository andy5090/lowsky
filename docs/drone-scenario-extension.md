# 드론 크기·역할·통신 방식 확장

## 현재 적용한 3D 외형과 크기

제작자 3D 보기는 `visual.airframe_id`로 14가지 외형을 선택한다. 세 케이스 모두 같은 순서로 기체를 배정한다. 관측 표식 세 종류와 독립적으로 순환하며, 역할·통신 상태·탐지 정답을 외형이나 색으로 표현하지 않는다. `public.json`, 에이전트 관측 스냅샷에는 기종을 추가하지 않는다.

| 외형 | 구현 | 기본 최대 수평 폭 |
| --- | --- | --- |
| 상용 쿼드콥터 | 무료 CesiumDrone GLB, 텍스처·카메라·프로펠러 애니메이션 | 0.6m |
| FPV | 노출 카본 프레임·배터리 스트랩·전방 카메라·안테나·3엽 프로펠러 | 0.6m |
| 헥사콥터 | 6개 모터·암·프로펠러, 하부 카메라·스키드 | 1.5m |
| Geran-2 / Shahed-136 | 델타익·끝단 수직핀·후방 프로펠러 | 3.5m |
| Geran-3 | 델타익·제트 흡입구와 배기구, 프로펠러 없음 | 3.5m |
| Garpiya | 별도 동체·날개 비율의 델타익 | 3.5m |
| Lancet | 전후 두 쌍의 X자 날개·광학부·후방 프로펠러 | 1.6m |
| Orlan-10 / Orlan-30 | 긴 주익·꼬리날개·전방 프로펠러, 다른 센서 크기와 동체 비율 | 3.1m |
| ZALA / Supercam | 서로 다른 후퇴각·날개 폭 비율·윙렛의 전익형 | 3.1m |
| Gerbera | 경량 델타익·중앙 수직꼬리 | 2.5m |
| Parodiya | 단순 주익·꼬리날개·가느다란 동체 | 2.0m |
| Molniya | 주익·쌍붐·연결된 꼬리날개 | 2.0m |

이는 **형상 구분을 위한 시각적 근사 모델**이며 실측 복제품이 아니다. 크기는 프로펠러 메시를 포함한 기준 포즈의 X/Z 최대 외접 폭이다. 회전 중 블레이드의 순간 외접 폭은 달라질 수 있으며 회전 원판 전체의 실측 직경을 의미하지 않는다. 날개 폭과 기체 길이 중 더 큰 값이므로 문서의 날개 폭과 같은 측정값으로 해석하지 않는다. 기존 0.6m 기준은 소형 멀티콥터에 유지하고, 고정익은 문서의 크기 등급을 참고한 잠정 표시 프로필로 구분했다. `LOW_SKY_scenario_v2.docx`의 기체 표와 `data/references/drone_sources.json`의 명칭을 참고했으며, 미검증 명칭·치수를 제조사 검증값으로 승격하지 않았다.

`godot/assets/display_profiles.json`에서 형상, 기본 크기, 근사 여부를 관리한다. `visual.size_profile`을 지정하면 기체 기본값보다 우선한다. 기종이 없거나 알려지지 않은 경우 기존 소형 쿼드콥터로 돌아간다. 역할이나 통신 방식으로 크기를 자동 결정하지 않는다. 로컬 좌표는 1단위=1m이고 경로·원점·기존 관측 시각은 유지한다.

`[` / `]`로 기체를 선택하면 제작자용 카메라 패널에 이름과 표시 크기가 나타난다. 추적 거리는 크기에 비례하고 기수는 기존 경로의 진행 방향을 따른다. 프로펠러 위상은 시뮬레이션 시각을 사용하므로 일시정지·시간 이동·연동 모드에서 따로 흘러가지 않는다. 가까운 150m 이내에서만 애니메이션을 갱신하며 먼 거리에서도 본체는 계속 존재한다. 정적 메시를 재질별로 병합하고 같은 기종끼리 공유해 240대 장면의 중복 생성을 줄였다.

[14종 렌더 비교](../artifacts/drone-catalog.png) · [FPV 추적 화면](../artifacts/drone-follow-fpv.png) · [무료 에셋 검토](drone-asset-review.md)

### 재현과 검증

```sh
python3 tools/fetch_drone_asset.py
python3 tools/scenario_dataset.py build
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_drone_models.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_drone_follow.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot --script res://tools/capture_drone_catalog.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot -- --capture --capture-airframe=fpv
```

## 다음 확장의 데이터 분리

아래 축 중 기체 외형과 크기는 위와 같이 구현했다. 역할·통신 매체·통신 상태의 확장은 아직 실행 데이터나 통신 시뮬레이터에 적용하지 않았다.

| 축 | 필드 제안 | 예시와 의미 |
| --- | --- | --- |
| 기체 | `airframe_id`, `visual.size_profile` | 형상과 크기. 소형 쿼드콥터 등 |
| 시나리오 역할 | `scenario_role` | `explosive_payload`, `decoy`, `unassigned`. 폭탄 탑재·디코이 등의 작성자용 역할 표기 |
| 통신 매체 | `link_medium` | `radio`, `fiber`, `hybrid`, `unknown` |
| 통신 상태 | `link_state` | `online`, `degraded`, `lost`, `unknown` |
| 관측 | 출처별 관측 시각·도착 시각·확인 항목 | 제작자 설정과 관측으로 확인된 정보를 구분 |

디코이는 기체 형식이 아니라 역할이다. 같은 형상·크기를 다른 역할로 사용할 수 있어야 하며, 화면의 크기나 재질에 평가 정답을 숨겨 넣지 않는다. `scenario_role`과 실제 통신 구성은 작성자 데이터에 두고, 에이전트에는 해당 시점에 공개된 관측·보고만 전달한다.

## 시나리오 초안

| 실험 | 추상 이벤트 | 확인할 동작 |
| --- | --- | --- |
| 정상 통신 | 무선·광섬유 객체의 기록이 정상 갱신 | 출처와 관측 시각을 정확히 표시 |
| 무선 채널 저하 | 재밍 상황을 사전 작성한 `radio_quality_degraded` 이벤트로 표현 | 해당 무선 링크의 지연·결측을 표시하고 마지막 기록을 새 관측으로 취급하지 않음 |
| 다른 통신 매체 | 같은 시각 광섬유 링크의 상태는 별도 이벤트로 관리 | 모든 객체를 일괄 통신 두절로 처리하지 않음 |
| 연결된 객체의 구역 진입 | 가상 경계 통과 시 `zone_entered` 관측 발행 | 링크 상태와 위치 관측의 근거를 각각 확인 |
| 역할 보고 충돌 | 같은 객체에 대해 역할 보고가 서로 다름 | 작성자 정답을 노출하지 않고 상충하는 보고와 미확인 항목을 설명 |

통신 상태와 이동 재생은 별개로 관리한다. `lost` 상태만으로 객체를 정지·삭제하지 않는다. 광섬유 링크도 별도의 손실·결측 이벤트를 가질 수 있으며, 통신 매체 이름만으로 모든 기능의 정상 여부를 단정하지 않는다.

첫 확장은 실제 장비 제어 대신 고정 타임라인의 상태 이벤트와 관측 기록을 사용한다. 기존 일치·충돌·결측 실험과 동일하게 설명의 근거, 최신성, 누락 처리를 평가한다.

## 검증 항목

- 표시 크기가 프로필의 최대 수평 폭과 일치하고 객체 원점·경로는 유지되는가.
- 무선 채널 저하가 다른 링크의 상태를 근거 없이 변경하지 않는가.
- 역할 정답·통신 구성·향후 이벤트가 관측 스냅샷으로 누출되지 않는가.
- 결측 중 화면이 마지막 관측 시각을 표시하고, 작성자 보기와 관측 보기를 구분하는가.
- 같은 관측 스냅샷으로 규칙 기준선과 에이전트 설명을 비교할 수 있는가.
