# LOW SKY 가상 공군 기지 시나리오 실험

배경은 **실존 장소를 재현하지 않는 가상의 공군 기지**, 아트 방향은 **실사 지향**으로 확정했다. 현재는 Godot 3D 제작자 보기와 별도의 웹 관측 모니터를 같은 재생 시계로 연결했다. 실제 지도 위 가상 기지 배치와 별도 평면도를 제공한다. Deep Agents와 설명 생성은 아직 연결하지 않았다.

원본 기획 문서는 로컬 참고 자료로 보관하며 공개 저장소에는 포함하지 않는다. 구현 범위는 `docs/mvp-direction.md`에서 확인할 수 있다. 외부 에셋의 출처와 라이선스는 각 `godot/third_party` 하위 폴더에 보관한다.

## 준비된 내용

- [시나리오 데이터셋](data/scenarios/v1/README.md): 12개 케이스, 관측 324건, 평가 체크포인트 144개.
- [구상 문서](docs/mvp-direction.md): 3D 시나리오·에이전트 실험의 범위.
- [드론 크기·역할·통신 확장](docs/drone-scenario-extension.md): 적용된 크기 기준과 통신 상태 시나리오 설계.
- `godot/assets/`: 직접 생성한 임시 GLB 7종과 매핑 목록.
- `godot/third_party/kenney_industrial/`: 외부 후보 모델 4종, 텍스처, 원본 라이선스와 출처 기록.
- `godot/third_party/realistic/`: PBR 재질 4세트, HDRI 하늘, Cesium 항공기와 라이선스·파일 해시.
- `godot/detailed_environment.gd`: 가상 지형, 상세 격납고·관제탑·보조 건물.
- `godot/plains_environment.gd`: 평야형 테스트 지형, 농경지 패턴과 절차 생성 수목대.
- `monitor/`: 영어 기본·한국어 선택 관측 모니터, 실제 지도 위 합성 오버레이와 별도 도면, 근거·현재 알림·확인 표시.
- `tools/monitor_server.py`: 표준 라이브러리 기반 로컬 서버와 공유 시계.
- `data/site_layout.json`: 가상 활주로 2,500 × 45m, 부지 2,500 × 4,000m, 높이 2.5m의 외곽 울타리. 설계 표준이나 실제 기지 치수의 재현이 아니다.
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

3D 지형은 [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/)의 N36E127 HGT를 bilinear 보간해 만들었다. 원본 체크섬, 출처, 처리 방법은 `data/terrain/`에 기록했다. 지형 원본 격자는 1각초이며 표시 격자는 50m다. 기준점 고도 373m를 로컬 Y=0으로 삼으며 수직 과장은 없다. **가상 기지와 주변 700m 전이 구간은 평탄화·보간으로 수정했다.** 이 부분은 실제 지형 재현이 아니다. 나머지 주변 지형은 DEM의 상대 고도를 사용한다. 위성사진·실제 건물·식생 분포는 반입하지 않아 텍스처는 예시 재질이다.

이전 우크라이나 참고 방향의 합성 평야 프리셋은 비교 모드로 남겨 두었다. 기본 지역은 이후 사용자 선택에 따라 한국으로 변경했다.

`LOW_SKY_scenario_v2.docx`는 최신 로컬 기획 참고 문서다. 원본은 공개 저장소에서 제외한다. 현재 실행 데이터는 여전히 12개 관측 품질 검증 케이스다. 문서의 6시점 구성, 공개 전조·센서 상태·불확실성 표시를 향후 데이터 계약으로 구체화해야 한다. 문서에서 언급한 `sim/raid.py`, `core/classify.py`는 이 저장소의 기존 구현이 아니다. v2의 전체 시나리오나 무기 선택·교전 권고는 구현하지 않았다.
