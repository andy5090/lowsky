# 이전 기준점 주변의 한국 지형과 Godot UI

지도·DEM과 같은 **37.90N, 127.20E**, 동서·남북 10 km 영역을 사용한다. X는 동쪽, Z는 남쪽이며, 영상의 위쪽이 북쪽이다. 가상 기지 내부는 기존 부지 평탄화와 시설 배치를 유지한다.

## 반영 내용

- 반복 잔디 바닥을 2021년 Sentinel-2 연간 합성 영상으로 대체했다. 가상 조성 부지에는 넓은 범위의 색상 변화와 서로 회전한 근거리 잔디 샘플을 섞어 반복 무늬를 줄였다.
- ESA WorldCover의 나무 덮임 영역에 침엽·활엽 형태 4종, 크기·방향·색상 변화가 있는 **300,000그루**를 배치했다. 개별 나무 위치는 결정론적 시각화 샘플이다. 기지 여유 구역, 도로, 건물 주변은 제외한다.
- OSM 도로 중심선 1,492개 중 화면 범위·기지 제외를 적용한 **1,253개**를 표시한다. 등록 건물 958개 중 가상 조성 부지와 겹치지 않는 윤곽 **260개**를 입체화했다. 도로는 여러 재질별 메시에 묶고 나무는 500 m 구역별 MultiMesh로 처리한다. 수목 수 상한은 300,000이다. 1.25 km 이상 떨어진 구역은 같은 위치·색상의 저비용 모델로 전환하고, 70 m 전환 여유를 둔다. 원거리 나무는 그림자 계산을 생략한다.
- 나무·건물·도로의 높이는 실제 렌더 삼각형에서 샘플링해 DEM의 bilinear 보간과 메시 사이 높이 차를 피한다.
- 버튼은 공통 테마 한 곳에서 배경, 테두리, 여백, hover·pressed·disabled·키보드 focus를 정의한다. 패널 오른쪽 위 **− / +** 버튼은 조작 영역을 접고 펼친다. 접으면 작은 제목 바만 남고 시간·선택·카메라 상태는 유지된다. 데스크톱 창 제어가 추가되거나 창 높이가 줄어도 본문은 스크롤되어 화면 안에 유지된다.

## 출처와 한계

무료 에셋과 데이터의 [출처·라이선스](../godot/assets/terrain/ATTRIBUTION.md), [원본 요청과 해시](../data/terrain/context_provenance.json)를 함께 보관한다. ESA 영상은 CC BY 4.0, OSM 데이터는 ODbL 1.0이다. 실행 중 외부 지도 서비스에 요청하지 않는다. OSM 배경 타일과 별개로, 재현 가능한 Overpass 원본 응답을 압축 보관했다.

이 영상은 **2021년 연간 합성**, OSM 원본의 데이터 시각은 **2026-10-10**이다. 최신 항공사진이 아니다. 영상 원본 10 m, DEM 표시 50 m의 해상도 한계 때문에 지상 가까이에서는 흐릿해진다. 나무 모양·위치·높이와 건물 재질은 단순화한 표현이며, OSM에 없는 건물은 임의로 추가하지 않는다. 층수만 있으면 층당 3 m, 정보가 없으면 아파트 18 m/기타 7.5 m로 표시한다. 도로 폭도 태그가 없으면 종류별 가정이다. 교량은 지면에 붙인 띠 형태이며, 다중 폴리곤 관계·복잡한 교차로 입체 구조·정밀 지붕은 구현하지 않았다. 이 배경 형상은 센서 관측·가림·충돌 계산을 바꾸지 않는다.

기준점이 바뀌면 `monitor/map_config.json`, DEM, 영상 범위, OSM 스냅샷을 함께 갱신해야 한다. 렌더러와 테스트는 원점·범위 불일치를 검사한다.

## 재현·검증

```sh
python3 tools/fetch_korean_context.py
python3 tools/build_korean_context.py
python3 -m unittest tests.test_korean_context
godot --path godot --script res://tools/verify_geographic_context.gd
godot --path godot --script res://tools/capture_geographic_context.gd
godot --path godot -- --capture --overview
```

이미지가 없는 경우만 `fetch_korean_context.py --download-missing`으로 복원한다. 해시가 바뀐 응답은 덮어쓰지 않고 오류를 낸다. Godot 검증은 MultiMesh와 실제 UI 입력을 검사하므로 OpenGL 창이 필요하다. 원본 검증, 좌표 왕복·영상 정렬, 지형 접지, 기지·도로 제외, 버튼 상태, 접기·펼치기의 상태 보존을 확인한다.

렌더 결과: [전체 조망](../artifacts/korea-overview.png), [숲](../artifacts/korea-forest.png), [마을](../artifacts/korea-town.png), [버튼 상태](../artifacts/korea-controls.png), [접은 패널](../artifacts/korea-panel-collapsed.png).
