# LOW SKY 가상 공군 기지 시나리오 실험

배경은 **실존 장소를 재현하지 않는 가상의 공군 기지**, 아트 방향은 **실사 지향**으로 확정했다. 현재는 합성 시나리오 데이터셋과 에셋을 확인하는 로컬 Godot 미리보기다. Deep Agents, 관측 전용 화면, 설명 카드와 사람의 검토 기록은 아직 연결하지 않았다.

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
- `godot/preview.gd`: 가상 장면 재생과 에셋 연결 확인. 실제 기지의 지리·운영 모델이 아니다.

## 실행

Godot 4.5에서 확인했다. 에디터에서 `godot/project.godot`를 열어 실행하거나 macOS에서는 아래 명령을 사용한다.

```sh
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```

숫자 1·2·3으로 세 갈래를 전환하고, Space로 재생을 멈추며, R로 처음으로 돌아간다. **왼쪽 또는 가운데 버튼 드래그는 패닝**, **오른쪽 또는 Shift+왼쪽 버튼 드래그는 회전**이다. 마우스 휠은 확대·축소, 좌우 화살표는 시점 회전, C는 현재 중심을 유지한 근경·전체 조망 전환, H는 최초 시점 복원이다. 조작 패널 밖에서 드래그를 시작한다. 현재 화면은 실제 경로를 보여주는 **제작자 보기**이며, 관측이 끊겨도 객체가 계속 움직이는 것이 정상이다. 관측 전용 UI로 오해하지 않도록 화면에 표시했다.

기본 화면은 PBR 재질을 입힌 상세 건물과 평야형 테스트 지형을 사용한다. **T 키 또는 Terrain 버튼**으로 기존 구릉 지형과 전환한다. 시나리오 시간·객체·갈래는 유지된다. 기존 지형으로 시작하려면 `-- --hills`를 붙인다. 스타일화 외부 모델은 `-- --stylized`, 임시 도형은 `-- --blockout`으로 비교한다. 현재는 실사 지향의 초기 장면이며 최종 실사 수준의 완성본은 아니다. 항공기는 시각 연결 확인용 샘플로, 최종 기종 선정과 교체는 남아 있다.

드론은 프로펠러 포함 최대 수평 폭 **0.6m**를 잠정 기준으로 표시한다. 설정은 `godot/assets/display_profiles.json`에 있으며, 객체별 `visual.size_profile`로 교체할 수 있다. 이 보정은 드론 표시 크기에 적용한 것으로 전체 기지의 실제 축척을 보장하지 않는다. 역할(폭탄 탑재·디코이 등), 통신 방식과 재밍·광섬유 관련 이벤트는 확장 문서에 정리한 설계 단계다.

## 재생성

```sh
python3 tools/scenario_dataset.py build
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/build_assets.gd
python3 tools/fetch_asset_sample.py
python3 tools/fetch_realistic_assets.py
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --editor --import
```

외부 다운로드 스크립트는 특정 버전 ZIP의 SHA-256을 확인하고 선택한 파일만 추출한다. 실사 재질 다운로드도 `provenance.json`에 기록된 출처와 체크섬을 확인한다. 다른 패키지를 설치하지 않는다. 원본이 변경되면 자동으로 새 버전을 받아들이지 않고 중단한다.

## 검증

```sh
python3 -m unittest discover -s tests -v
python3 tools/scenario_dataset.py validate
python3 -m compileall -q tools tests
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_preview.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot --script res://tools/verify_preview.gd
/Applications/Godot.app/Contents/MacOS/Godot --path godot -- --capture
```

창을 표시하는 검증 명령은 실제 GUI 입력 경로에서 패닝·회전·버튼 클릭의 공존도 검사한다. Headless 실행에서는 렌더링이 필요한 GUI 버튼 전달 검사만 건너뛴다.

마지막 명령은 평야형 장면을 렌더링해 `artifacts/plains-preview.png`를 저장하고 종료한다. `--capture --overview`는 전체 조망을 `artifacts/plains-overview.png`에 저장한다. `--hills`를 추가하면 기존 지형을 `artifacts/asset-preview.png` 또는 `artifacts/asset-overview.png`에 저장한다. 그래픽 장치가 필요하다. 자동 검증과 실제 렌더 확인은 에셋 연결의 증거이며, 완성된 에이전트 시스템의 검증을 의미하지 않는다.

## 3D 품질과 출처

외부 모델의 품질과 실제 장소의 재현 정확도는 별도 항목이다. 외부 모델은 형태·재질의 완성도를 높이는 데 활용하고, 크기·피벗·배치는 장면에서 맞춘다. 상세 모델을 쓰더라도 실제 장소를 실측한 것처럼 표시하지 않는다.

현재 반입한 [Kenney City Kit Industrial](https://kenney.nl/assets/city-kit-industrial)은 CC0 스타일화 모델이며 실사 모델이 아니다. 정확한 출처, 파일 해시, 수정 여부는 `godot/third_party/kenney_industrial/provenance.json`에 보관했다. 격납고로 사용하는 건물도 가상 장면용 대체 모델이다.

현재 [Poly Haven](https://polyhaven.com/license)의 CC0 PBR 재질 4세트(콘크리트·금속·아스팔트·초지)와 HDRI를 적용했다. [Cesium 항공기 샘플](https://github.com/CesiumGS/cesium/tree/main/Apps/SampleData/models/CesiumAir)은 원본 라이선스를 함께 보관하며 장면용으로 크기만 정규화했다. 모든 외부 원본 파일은 변경하지 않았고 재질 배율·색상은 Godot에서 조절한다. 출처는 `godot/third_party/realistic/provenance.json`에 있다.

지형·건물 배치는 독자적으로 구성했고 실제 위도·경도나 특정 기지 자료를 사용하지 않았다. Google Maps/Earth 데이터는 반입하거나 연결하지 않았다. 가상 기지이므로 지도 서비스 연결 없이 실행된다.

배경 참고 지역은 미정이며 우크라이나가 후보로 제시됐다. 사용자의 테스트 적용 요청에 따라 평야·완만한 기복·농경지·수목대를 조합한 **가상 지형 프리셋 하나**를 적용했다. 기존 재질을 재사용하며 추가 다운로드나 패키지 설치는 없다. 실제 지역 고도 자료를 사용하지 않았고 수목은 중거리 표현용 절차 모델이다. 특정 지역 재현 정확도나 최종 실사 품질을 보장하는 장면은 아니다.

현재 남은 작업은 최종 환경 미술(지형·식생·항공기 등), 관측 전용 UI, Deep Agents 연결, 설명 비교와 사람 검토 기록이다. 우선 이 미리보기에서 가상 배치와 시나리오 연결을 검증할 수 있다.
