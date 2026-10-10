# 무료 드론 3D 에셋 검토

2026-10-11 검토. 형상·재질·라이선스·직접 다운로드 가능 여부를 확인했다. 모델 종류가 문서와 맞고, 출처를 함께 배포할 수 있으며, 240대 장면에서 사용할 수 있는 가벼운 자료를 우선했다.

| 후보 | 확인한 조건 | 결과 |
| --- | --- | --- |
| [CesiumDrone](https://github.com/CesiumGS/cesium/tree/171498f00f08e45d4e6315bb8606bf28b970d099/Apps/SampleData/models/CesiumDrone) | GLB 1,169,536 bytes, 3,412 triangles, 7 meshes, 내장 텍스처와 Fly 애니메이션. 파일 내부 `asset.copyright`에 Ed Mackey / Analytical Graphics, Inc., CC BY 4.0 명시 | **채택**. 상용 쿼드콥터 표시, 원본 GLB 유지. 런타임에서 회전·축척·시뮬레이션 시각에 따른 애니메이션만 적용 |
| [Drone — alexandre.ltrgn](https://sketchfab.com/3d-models/drone-688425e1cddb4a288a12b00246a76d43) | 페이지에 무료 다운로드·CC Attribution·37.2k triangles 표기 | 고품질 교체 후보. 이 작업에서는 파일을 내려받지 않아 텍스처·Godot 호환성을 검증하지 않음. 채택 모델보다 메시 수가 많음 |
| [Shahed 136 — faintastic18](https://sketchfab.com/3d-models/shahed-136-bc8754128c9d48c48baadeff1db8f0c7) | 페이지에 무료 다운로드·CC Attribution·41.9k triangles 표기 | 문서 기종과 맞는 차기 후보. 파일 반입·라이선스 버전·재질 확인과 경량화가 필요하므로 미채택 |
| [Shahed-136 STL — idmental.id](https://commons.wikimedia.org/wiki/File:Shahed-136.stl) | Commons의 CC BY 4.0 표기, STL 3.4 MB | 텍스처 없는 STL이므로 재질 작업과 메시 변환이 필요. 이번에는 외형 참고 후보로만 보관 |
| [Innerscene quadcopter](https://www.innerscene.com/tools/library/3d-parts/quadcopter-with-flight-electronics-a25968c1) | 검색 결과에는 CC0·GLB·268 KB 명시 | 원본 페이지가 HTTP 403을 반환해 라이선스 원문과 파일을 직접 확인하지 못함. 미반입 |
| [NASA Global Hawk](https://science.nasa.gov/3d-resources/global-hawk/) | NASA 공식 페이지에 GLB 직접 다운로드 제공 | 문서에서 대형 정찰기는 현재 데모 범위 밖이므로 이번 시나리오에는 미채택 |

CesiumDrone은 저장소 코드의 Apache 라이선스를 그대로 추정하지 않고 **GLB 내부의 에셋별 CC BY 4.0 표기**를 사용했다. 제작자 크레딧·출처·라이선스 링크·수정 내역은 `godot/third_party/realistic/cesium_drone/ATTRIBUTION.md`와 `LICENSE.txt`에 있고, 고정 커밋 URL·SHA-256·크기는 `provenance.json`에 기록했다. `python3 tools/fetch_drone_asset.py`는 같은 원본만 복원하며 체크섬이 다르면 중단한다. Godot 배포 설정은 이 폴더의 `.md`, `.txt`, `.json`도 포함한다.

그 외 기체는 `godot/drone_models.gd`의 자체 생성 메시를 사용한다. 문서의 기종 구분을 반영한 근사 외형이며 실물 치수·제조사 형상·비행 성능을 검증한 모델이 아니다. 기존 임시 GLB는 `--blockout` 비교와 이전 형상 확인용으로 유지한다. 새 패키지 의존성은 추가하지 않았다.
