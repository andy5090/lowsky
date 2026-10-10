# LOW SKY 가상 공군 기지 시나리오 실험

배경은 **실존 장소를 재현하지 않는 가상의 공군 기지**, 아트 방향은 **실사 지향**으로 확정했다. 현재는 Godot 3D 제작자 보기와 별도의 웹 관측 모니터를 같은 재생 시계로 연결했다. 실제 지도 위 가상 기지 배치와 별도 평면도를 제공한다. Deep Agents와 설명 생성은 아직 연결하지 않았다.

원본 기획 문서는 로컬 참고 자료로 보관하며 공개 저장소에는 포함하지 않는다. 구현 범위는 `docs/mvp-direction.md`에서 확인할 수 있다. 외부 에셋의 출처와 라이선스는 각 `godot/third_party` 하위 폴더에 보관한다.

## 준비된 내용

- [시나리오 데이터셋](data/scenarios/v1/README.md): 12개 케이스, 관측 324건, 평가 체크포인트 144개.
- [구상 문서](docs/mvp-direction.md): 3D 시나리오·에이전트 실험의 범위.
- [드론·출처 참고 카탈로그](data/references/drone_sources.json): 사용자 제공 9개 명칭·분류와 10개 출처. 개별 주장 검증 전이며 실행 시나리오와 분리해 보관한다.
- [드론 크기·역할·통신 확장](docs/drone-scenario-extension.md): 적용된 크기 기준과 통신 상태 시나리오 설계.
- `godot/assets/`: 직접 생성한 임시 GLB 7종과 매핑 목록.
- `godot/third_party/kenney_industrial/`: 외부 후보 모델 4종, 텍스처, 원본 라이선스와 출처 기록.
- `godot/third_party/realistic/`: PBR 재질 4세트, HDRI 하늘, Cesium 항공기와 라이선스·파일 해시.
- `godot/detailed_environment.gd`: 가상 지형, 상세 격납고·관제탑·보조 건물.
- `godot/plains_environment.gd`: 평야형 테스트 지형, 농경지 패턴과 절차 생성 수목대.
- `monitor/`: 영어 기본·한국어 선택 관측 모니터, 실제 지도 위 합성 오버레이와 별도 도면, 근거·현재 알림·확인 표시.
- `tools/monitor_server.py`: 표준 라이브러리 기반 로컬 서버와 공유 시계.
- `data/site_layout.json`: 가상 활주로 2,500 × 45m, 부지 1,200 × 2,900m (3.48㎢), 높이 2.5m의 외곽 울타리. 설계 표준이나 실제 기지 치수의 재현이 아니다.
- `data/terrain/korea_site.json`: 한국 임의 지점(36.5N, 127.8E) 주변 공개 DEM을 10km × 10km, 50m 격자로 변환한 지형.
- `godot/preview.gd`: 가상 장면 재생과 에셋 연결 확인. 실제 기지의 지리·운영 모델이 아니다.

## 실행

Godot 4.5에서 확인했다. 에디터에서 `godot/project.godot`를 열어 실행하거나 macOS에서는 아래 명령을 사용한다.

```sh
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```

모니터링과 3D를 함께 실행하려면 서버를 먼저 켠다.

```sh
python3 tools/monitor_server.py
# 다른 터미널에서:
/Applications/Godot.app/Contents/MacOS/Godot --path godot -- --monitor
```

브라우저에서 http://127.0.0.1:8765 를 연다. 기본 언어는 영어이며 상단에서 한국어로 바꿀 수 있다. 언어 선택은 해당 브라우저에 저장된다. 모니터의 재생·일시정지·시간 이동·케이스·배속 조작이 Godot에 반영된다. `--monitor`에서는 3D의 재생 조작을 비활성화하고 카메라·지형 조작만 허용한다. 연결이 끊기면 3D 재생을 멈추며, 재연결 시 서버 시간으로 맞춘다. 기본 포트는 8765이다.

모니터는 현재까지 도착한 관측만 보여준다. 위치는 30초 간격의 마지막 관측이며 보간된 제작자 경로가 아니다. 충돌·채널 중단·오래된 위치 알림은 관측 품질에 관한 것이다. 알림 확인은 현재 실행의 메모리 상태이며 영구 감사 로그가 아니다. 시간 이동·케이스 변경·초기화 시 확인 상태를 지운다. 관측 채널 A/B는 실제 RF·광섬유 통신 모델이 아니다.

서버 없이 Godot를 실행하면 독립 재생 모드다. 숫자 1·2·3으로 세 갈래를 전환하고, Space로 재생을 멈추며, R로 처음으로 돌아간다. **왼쪽 또는 가운데 버튼 드래그는 패닝**, **오른쪽 또는 Shift+왼쪽 버튼 드래그는 회전**이다. 마우스 휠은 확대·축소, 좌우 화살표는 시점 회전, C는 기지 근경·전체 조망 전환, H는 최초 시점 복원이다. 조작 패널 밖에서 드래그를 시작한다. 현재 화면은 실제 경로를 보여주는 **제작자 보기**이며, 관측이 끊겨도 객체가 계속 움직이는 것이 정상이다. 관측 전용 UI로 오해하지 않도록 화면에 표시했다.

기본 화면은 한국 지도 기준점과 일치하는 공개 고도 지형을 사용한다. **T 키 또는 Terrain 버튼**은 한국 DEM → 합성 평야 → 합성 구릉을 순환한다. 시나리오 시간·객체·갈래는 유지된다. `-- --plains`, `-- --hills`로 합성 프리셋을 바로 선택할 수 있다. 스타일화 외부 모델은 `-- --stylized`, 임시 도형은 `-- --blockout`으로 비교한다. 현재는 실사 지향의 초기 장면이며 최종 환경 미술과 항공기 교체는 남아 있다.

드론은 프로펠러 포함 최대 수평 폭 **0.6m**를 잠정 기준으로 표시한다. 설정은 `godot/assets/display_profiles.json`에 있으며, 객체별 `visual.size_profile`로 교체할 수 있다. 공통 로컬 좌표는 1단위=1m이며 활주로·울타리·지도 오버레이가 같은 배치를 사용한다. 건물과 항공기는 시각화용 샘플이다. 역할(폭탄 탑재·디코이 등), 통신 방식과 재밍·광섬유 관련 이벤트는 확장 문서에 정리한 설계 단계다.

케이스 선택 아래 **Scenario briefing / 시나리오 설명**에서 목적과 대상 수를 확인하고, **Timeline & review points / 진행 순서와 확인 포인트**를 펼치면 주요 시점과 검토 기준을 볼 수 있다. 12개 케이스는 4개 대상 묶음 × 일치·충돌·결측 3가지 변형이다. 설명은 [생성된 브리핑 데이터](data/scenarios/v1/briefings.json)와 영어·한국어 문구로 구성되며, 이후 이벤트가 포함된 운영자용 설명이다. 관측 전용 `/api/state`·`/api/clock`과 분리된 `/api/briefings`에서 제공한다. 민간 지역 조기 신호는 모든 케이스에 공통인 별도 피드다.

지도 **Radar overlay / 레이더 표시**는 채널 A/B의 수신 관측을 시각화한다. 재생 시 스캔이 회전하고 새 관측이 도착하는 00:00·00:30·01:00 등의 시점에 표식이 나타난다. 일시정지·시간 이동은 공유 시계를 따르며 중단된 채널은 스캔과 새 표식을 표시하지 않는다. [레이더 표시 설정](data/radar_display.json)의 12초 스캔 주기·1,000m 원·2.5초 표식은 시각화 가정이며 탐지 범위·물리 스캔 모델이 아니다. 표식은 공개 관측의 위치만 사용하며 제작자용 world 데이터나 추정 경로를 사용하지 않는다.

지도 부지는 **Fictional terrain replacement / 가상 조성 구역**으로 표시한다. 내부 OSM 도로·지형은 불투명한 합성 부지로 대체하고 주변 실제 지도는 유지한다. 기존 좌표를 유지해 한국 DEM·3D와 일치시키며, 실제 토지의 공항 적합성이나 도로 이설을 의미하지 않는다. 3D는 동일 울타리 + 50m 여유 구역을 평탄화하고 바깥 350m를 DEM으로 연결한다.

**Simulation motion / 가상 이동 표시**를 켜면 보라색 `SIM` 드론 세 대가 부지 외곽에서 안쪽으로 2분간 이동한다. 지도와 Godot는 같은 world 키프레임·공유 시계를 사용한다. 지도 아이콘은 식별용 고정 크기이며 Godot 모델 폭 0.6m와 구분한다. 관측 표식은 여전히 수신된 30초 간격 위치만 사용한다. 제작자용 `/api/preview`의 연속 이동은 경고·에이전트 입력·레이더 탐지 판정에 사용하지 않는다.

## 민간 지역 조기 신호 데모

모니터의 **Community early signals / 민간 지역 조기 신호**는 음향 센서와 시민 앱 제보를 별도 출처로 보여준다. [입력 데이터](data/early_warning_demo.json)는 기존 12개 품질 테스트 케이스와 같은 시계를 사용하는 독립 합성 피드다. 기존 object 트랙의 정체·레이더 탐지 여부와 자동 연결하지 않으며, 실제 주민·휴대폰·음성을 수집하지 않는다. 지도 A/B/C 구역은 실제 주거지 조사 결과가 아니라 가상의 제보 지역이다.

- 00:10: A 구역 음향 후보 신호 → 단일 출처 경고.
- 00:22: 00:18에 작성된 앱 제보 도착 → 복수 출처 신호.
- 00:28: 음향 미보고와 앱 제보가 상충 → 상충 표시.
- 00:42: 새 음향·앱 제보가 함께 유효 → 복수 출처 신호.
- 00:45: B 구역 지연 제보 도착.
- 01:13: A/B의 신호가 유효시간을 초과 → 과거 근거는 유지하고 현재 경고는 해제. 안전이 확인되었다는 뜻이 아니다.
- 01:20: B 구역 제보 채널 중단. C 구역은 측정 불가와 음성(후보 미보고) 관측의 차이를 보여준다.

카드의 **Locate area / 구역 보기**로 지도에 초점을 맞추고 **Reports & sensor status / 제보·센서 상태**에서 관측·수신 시각, 품질, 분류기 점수와 근거 ID를 확인한다. 점수는 합성 입력값이며 공격 확률이 아니다. 30초 유효시간, 지도 구역 크기와 모든 이벤트는 데모 가정이다. 경고 확인은 해당 근거에만 적용되며 새 근거 도착 시 다시 경고한다. 확인 시각은 현재 실행의 이벤트 기록에 표시하고 서버 메모리에 최대 1,000건 보관한다. 영구 감사 로그는 아니며 서버 재시작 시 사라진다.

[민수용 참고 스펙](data/sensors/civilian_reference_specs.json)은 Infineon IM69D130 마이크와 Raspberry Pi Zero 2 W 처리 보드의 제조사 공개값을 보관한다. 마이크 SNR 69 dB(A)는 데이터시트 시험조건의 부품 특성이며 탐지 거리가 아니다. PDM 입력 변환·드라이버 등 연결 구성은 미선정·미검증이며 이 두 부품을 바로 연결할 수 있다는 의미가 아니다. 실제 드론 탐지 거리·정확도·오경보율은 미검증(null)으로 둔다. 데이터시트 URL·개정판·페이지·시험조건을 카탈로그에서 확인할 수 있다.

`LOW_SKY_picket_line.docx`의 반영 상태는 [문서 검토 기록](data/references/picket_line_review.json)에 정리했다. 음향·RF·EO/열영상의 입력 역할, 관측/수신 시각, 통신 중단과 원인 불명의 구분을 스펙 요구사항에 추가했다. RF·열영상 하드웨어, 엣지 추론, 실제 저장 후 재전송은 미구현이다. 문서의 20개 센서·장시간 재생·60/180초 기준은 제안으로 남겨 현재 데모 값과 구분한다.

레이더는 민수용 제한을 적용하지 않는다. [대드론 레이더 참고 스펙](data/sensors/radar_reference_specs.json)은 [Robin Radar IRIS 공식 제품 문서](https://www.robinradar.com/hubfs/Iris%20Datasheet%20V15.7_Online.pdf)의 `RRS.IRIS.A2.2026.04` 판을 사용한다. FMCW/X-band, 방위 360°·고각 60°, 계기상 범위 5/12km, 1초 갱신과 인터페이스를 출처와 함께 기록했다. 계기상 범위·탐지 거리·분류 거리는 서로 다르며, 현재 레이더 원의 크기와 스캔 속도는 별도 데모 가정이다. 특정 기종의 실제 탐지 성능을 재현하지 않는다.

우크라이나 [ePPO 개발자 앱 설명](https://play.google.com/store/apps/details?id=ua.quick.brpg.pathfinder)은 시민이 관측한 비행체·소리를 제보하는 방식이다. [미 육군의 음향 센서 사례 소개](https://www.lineofdeparture.army.mil/Journals/Air-Defense-Artillery/ADA-Archive/2024-E-Edition/Mobility-Matters/)에 나오는 Android 기기 포함 설치형 센서와 개인 휴대폰의 자동 감지를 같은 것으로 취급하지 않는다. 이 구현은 두 입력 유형의 합성 관측만 재생한다.

로컬 Sensor Engineering Brief와 Technical Specifications의 관측 상태·시간·불확실성 원칙을 반영했다. 두 원본 DOCX는 수정하거나 공개 저장소에 포함하지 않았다. JSON 변경 후 서버를 재시작하면 입력과 평가가 바뀐다. 새 패키지는 필요 없다.

## 재생성

```sh
python3 tools/scenario_dataset.py build
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/build_assets.gd
python3 tools/fetch_asset_sample.py
python3 tools/fetch_realistic_assets.py
python3 tools/fetch_korean_terrain.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
```

외부 다운로드 스크립트는 특정 버전 ZIP의 SHA-256을 확인하고 선택한 파일만 추출한다. 실사 재질 다운로드도 `provenance.json`에 기록된 출처와 체크섬을 확인한다. 다른 패키지를 설치하지 않는다. 원본이 변경되면 자동으로 새 버전을 받아들이지 않고 중단한다.

## 검증

```sh
python3 -m unittest discover -s tests -v
python3 tools/scenario_dataset.py validate
python3 -m compileall -q tools tests
node --check monitor/app.js
node tests/monitor_geo.mjs
node tests/monitor_radar.mjs
node tests/monitor_motion.mjs
node tests/test_monitor_i18n.mjs
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_preview.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot --script res://tools/verify_preview.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot -- --capture
```

창을 표시하는 검증 명령은 실제 GUI 입력 경로에서 패닝·회전·버튼 클릭의 공존도 검사한다. Headless 실행에서는 렌더링이 필요한 GUI 버튼 전달 검사만 건너뛴다.

마지막 명령은 한국 DEM 장면을 렌더링해 `artifacts/korea-preview.png`를 저장하고 종료한다. `--capture --overview`는 전체 조망을 `artifacts/korea-overview.png`에 저장한다. `--plains`는 `plains-*` 파일로 저장한다. `--hills`를 추가하면 기존 지형을 `artifacts/asset-preview.png` 또는 `artifacts/asset-overview.png`에 저장한다. 그래픽 장치가 필요하다. 자동 검증과 실제 렌더 확인은 에셋 연결의 증거이며, 완성된 에이전트 시스템의 검증을 의미하지 않는다.

## 3D 품질과 출처

외부 모델의 품질과 실제 장소의 재현 정확도는 별도 항목이다. 외부 모델은 형태·재질의 완성도를 높이는 데 활용하고, 크기·피벗·배치는 장면에서 맞춘다. 상세 모델을 쓰더라도 실제 장소를 실측한 것처럼 표시하지 않는다.

현재 반입한 [Kenney City Kit Industrial](https://kenney.nl/assets/city-kit-industrial)은 CC0 스타일화 모델이며 실사 모델이 아니다. 정확한 출처, 파일 해시, 수정 여부는 `godot/third_party/kenney_industrial/provenance.json`에 보관했다. 격납고로 사용하는 건물도 가상 장면용 대체 모델이다.

현재 [Poly Haven](https://polyhaven.com/license)의 CC0 PBR 재질 4세트(콘크리트·금속·아스팔트·초지)와 HDRI를 적용했다. [Cesium 항공기 샘플](https://github.com/CesiumGS/cesium/tree/main/Apps/SampleData/models/CesiumAir)은 원본 라이선스를 함께 보관하며 장면용으로 크기만 정규화했다. 모든 외부 원본 파일은 변경하지 않았고 재질 배율·색상은 Godot에서 조절한다. 출처는 `godot/third_party/realistic/provenance.json`에 있다.

지도는 [OpenStreetMap](https://www.openstreetmap.org/copyright)을 배경으로 사용한다. 한국 중부의 임의 기준점 36.5N, 127.8E에 가상 기지를 겹쳐 그린다. 실제 시설 위치나 해당 토지의 용도를 뜻하지 않는다. `monitor/map_config.json`에서 기준점을 관리하며, 변경 시 고도 데이터를 함께 재생성해야 한다. X는 동쪽, Z는 남쪽이다. 소규모 영역에 대한 구면 근사로 지도에 투영하므로 측량용 좌표 변환은 아니다.

OSM 타일은 브라우저에 보이는 영역만 요청하며 attribution을 표시한다. 일괄 수집·오프라인 저장을 하지 않는다. [타일 사용 정책](https://operations.osmfoundation.org/policies/tiles/)을 따른다. 자동 UI 검증에는 `?tiles=off`를 사용한다. 기지 평면도와 3D는 타일 네트워크 없이 동작한다. Google Maps/Earth 자료는 사용하지 않는다.

3D 지형은 [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/)의 N36E127 HGT를 bilinear 보간해 만들었다. 원본 체크섬, 출처, 처리 방법은 `data/terrain/`에 기록했다. 지형 원본 격자는 1각초이며 표시 격자는 50m다. 기준점 고도 373m를 로컬 Y=0으로 삼으며 수직 과장은 없다. **가상 기지와 주변 350m 전이 구간은 평탄화·보간으로 수정했다.** 이 부분은 실제 지형 재현이 아니다. 나머지 주변 지형은 DEM의 상대 고도를 사용한다. 위성사진·실제 건물·식생 분포는 반입하지 않아 텍스처는 예시 재질이다.

이전 우크라이나 참고 방향의 합성 평야 프리셋은 비교 모드로 남겨 두었다. 기본 지역은 이후 사용자 선택에 따라 한국으로 변경했다.

`LOW_SKY_scenario_v2.docx`는 최신 로컬 기획 참고 문서다. 원본은 공개 저장소에서 제외한다. 현재 실행 데이터는 여전히 12개 관측 품질 검증 케이스다. 문서의 6시점 구성, 공개 전조·센서 상태·불확실성 표시를 향후 데이터 계약으로 구체화해야 한다. 문서에서 언급한 `sim/raid.py`, `core/classify.py`는 이 저장소의 기존 구현이 아니다. v2의 전체 시나리오나 무기 선택·교전 권고는 구현하지 않았다.
