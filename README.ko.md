# LOW SKY 가상 공군 기지 시나리오 실험

[English](README.md)

<img src="monitor/logo-metal.png" alt="LOW SKY 메탈 항공 휘장 아이콘" width="144" height="144">

배경은 **실존 장소를 재현하지 않는 가상의 공군 기지**, 아트 방향은 **실사 지향**으로 확정했다. 현재는 Godot 3D 제작자 보기와 별도의 웹 관측 모니터를 같은 재생 시계로 연결했다. 실제 지도 위 가상 기지 배치와 별도 평면도를 제공한다. 전체 상황 평가, 수신 근거 설명, 사람의 검토 기록을 제공한다. Deep Agents는 선택형 LLM 연동이며, 모델 설정이 없으면 규칙 기반 요약임을 화면에 명시한다.

원본 기획 문서는 로컬 참고 자료로 보관하며 공개 저장소에는 포함하지 않는다. 구현 범위는 `docs/mvp-direction.md`에서 확인할 수 있다. 외부 에셋의 출처와 라이선스는 각 `godot/third_party` 하위 폴더에 보관한다.

## 준비된 내용

- [시나리오 데이터셋](data/scenarios/v1/README.md): 대표 시나리오 3개(12·24·240개 대상), 관측 6,876건, 평가 체크포인트 1,380개. 부하 시험은 마지막 1개만 제공한다.
- [구상 문서](docs/mvp-direction.md): 3D 시나리오·에이전트 실험의 범위.
- [드론·출처 참고 카탈로그](data/references/drone_sources.json): 사용자 제공 9개 명칭·분류와 10개 출처. 개별 주장 검증 전이며 실행 시나리오와 분리해 보관한다.
- [드론 크기·역할·통신 확장](docs/drone-scenario-extension.md): 적용된 크기 기준과 통신 상태 시나리오 설계.
- `godot/assets/`: 직접 생성한 임시 GLB 7종과 매핑 목록.
- `godot/third_party/kenney_industrial/`: 외부 후보 모델 4종, 텍스처, 원본 라이선스와 출처 기록.
- `godot/third_party/realistic/`: PBR 재질 4세트, HDRI 하늘, Cesium 항공기와 라이선스·파일 해시.
- `godot/detailed_environment.gd`: 가상 지형, 상세 격납고·관제탑·보조 건물.
- `godot/plains_environment.gd`: 평야형 테스트 지형, 농경지 패턴과 절차 생성 수목대.
- `monitor/`: 영어 기본·한국어 선택 **Decision making workspace**, 케이스별 설명, 가상 조성 구역, 수신 후 탐지 표시, 관측 근거·현재 알림·확인 표시.
- `tools/monitor_server.py`: 표준 라이브러리 기반 로컬 서버와 공유 시계.
- `data/site_layout.json`: 가상 활주로 2,500 × 45m, 외접 크기 1,200 × 2,900m의 비정형 12각 부지, 높이 2.5m의 외곽 울타리. 설계 표준이나 실제 기지 치수의 재현이 아니다.
- `data/terrain/korea_site.json`: 한국 임의 지점(36.23N, 127.08E) 주변 공개 DEM을 10km × 10km, 50m 격자로 변환한 지형.
- `godot/preview.gd`: 가상 장면 재생과 에셋 연결 확인. 실제 기지의 지리·운영 모델이 아니다.

## 로고

LOW SKY 아이콘은 브러시드 실버 메탈·건메탈 방패, 공군을 연상시키는 각진 날개, 저고도 감지 아치와 지평선을 조합했다. 특정 국가나 실제 부대의 공식 휘장이 아닌 가상 프로젝트용 디자인이다.

- [투명 배경 PNG](monitor/logo-metal.png): 웹 헤더와 브라우저 파비콘에 적용. 헤더 표시 크기는 데스크톱 52px, 모바일 42px이다.
- [생성 기록과 전체 프롬프트](monitor/logo-metal.provenance.json): 내장 `image_gen` 도구로 생성한 날짜·방식·요청 내용을 보관한다.
- 이전 [벡터 아이콘](monitor/logo.svg)은 비교용으로 보관하며 현재 헤더·파비콘은 새 PNG를 사용한다.

로고 이미지에 글자를 넣지 않고 `LOW SKY` 텍스트를 HTML로 유지해 작은 화면에서도 이름을 읽기 쉽게 했다.

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

브라우저에서 http://127.0.0.1:8765 를 연다. 기본 언어는 영어이며 상단에서 한국어로 바꿀 수 있다. 언어 선택은 해당 브라우저에 저장된다. 모니터의 재생·일시정지·시간 이동·케이스·배속 조작이 Godot에 반영된다. `--monitor`에서는 3D의 재생 조작을 비활성화하고 카메라·지형 조작만 허용한다. 연결이 끊기면 3D 재생을 멈추며, 재연결 시 서버 시간으로 맞춘다. 기본 포트는 8765이다. 웹 재생 버튼은 Godot를 자동 실행하지 않으므로 위 명령으로 3D 창도 열어야 한다. 연동 모드는 전체 조망으로 시작하며, 기본적으로 신선한 수신 탐지가 있는 드론에만 3D 라벨과 화면 표식을 표시한다. **Show drone positions (SIM)** 스위치는 기본 꺼짐이며, 켜면 미탐지 드론까지 보라색 SIM 라벨로 표시한다. 드론의 물리 모델은 계속 이동한다. 지도에도 독립적인 **드론 위치 보기** 스위치가 있으며, 켠 경우에만 별도 보라색 SIM 위치 레이어를 표시한다. **F 키 또는 Follow first drone 버튼**은 첫 드론을 가까이 따라보고, 다시 누르면 전체 조망으로 돌아간다. 카메라 수동 조작은 따라보기를 해제한다. 모델의 실제 폭 0.6m는 유지한다.

모니터는 현재까지 도착한 관측만 보여준다. 위치는 10초 간격 합성 데이터 중 마지막 수신 관측이며 보간된 제작자 경로가 아니다. 충돌·채널 중단·오래된 위치 알림은 관측 품질에 관한 것이다. 알림 확인은 현재 실행의 메모리 상태이며 영구 감사 로그가 아니다. 시간 이동·케이스 변경·초기화 시 확인 상태를 지운다. 관측 채널 A/B는 실제 RF·광섬유 통신 모델이 아니다.

서버 없이 Godot를 실행하면 독립 재생 모드다. 숫자 1·2·3으로 세 갈래를 전환하고, Space로 재생을 멈추며, R로 처음으로 돌아간다. **왼쪽 또는 가운데 버튼 드래그는 패닝**, **오른쪽 또는 Shift+왼쪽 버튼 드래그는 회전**이다. 마우스 휠은 확대·축소, 좌우 화살표는 시점 회전, C는 기지 근경·전체 조망 전환, H는 최초 시점 복원이다. 조작 패널 밖에서 드래그를 시작한다. 현재 화면은 실제 경로를 보여주는 **제작자 보기**이며, 관측이 끊겨도 객체가 계속 움직이는 것이 정상이다. 관측 전용 UI로 오해하지 않도록 화면에 표시했다.

기본 화면은 한국 지도 기준점과 일치하는 공개 고도 지형을 사용한다. **T 키 또는 Terrain 버튼**은 한국 DEM → 합성 평야 → 합성 구릉을 순환한다. 시나리오 시간·객체·갈래는 유지된다. `-- --plains`, `-- --hills`로 합성 프리셋을 바로 선택할 수 있다. 스타일화 외부 모델은 `-- --stylized`, 임시 도형은 `-- --blockout`으로 비교한다. 현재는 실사 지향의 초기 장면이며 최종 환경 미술과 항공기 교체는 남아 있다.

드론은 프로펠러 포함 최대 수평 폭 **0.6m**를 잠정 기준으로 표시한다. 설정은 `godot/assets/display_profiles.json`에 있으며, 객체별 `visual.size_profile`로 교체할 수 있다. 공통 로컬 좌표는 1단위=1m이며 활주로·울타리·지도 오버레이가 같은 배치를 사용한다. 건물과 항공기는 시각화용 샘플이다. 역할(폭탄 탑재·디코이 등), 통신 방식과 재밍·광섬유 관련 이벤트는 확장 문서에 정리한 설계 단계다.

케이스 선택 아래 **Scenario briefing / 시나리오 설명**에서 목적과 대상 수를 확인하고, **Timeline & review points / 진행 순서와 확인 포인트**를 펼치면 주요 시점과 검토 기준을 볼 수 있다. 3개 케이스는 혼재된 비행체의 첫 탐지(12개), 식별 상충과 재확인(24개), 모니터링 부하 시험·채널 단절과 복구(240개)다. 부하 시험은 세 번째 하나만 해당한다. 각각 180초이며, 숫자는 실측 공격 규모가 아닌 합성 장면 가정이다. 설명은 [생성된 브리핑 데이터](data/scenarios/v1/briefings.json)와 영어·한국어 문구로 구성되며, 이후 이벤트가 포함된 운영자용 설명이다. 관측 전용 `/api/state`·`/api/clock`과 분리된 `/api/briefings`에서 제공한다. 민간 지역 조기 신호는 모든 케이스에 공통인 별도 피드다.

지도 **Radar overlay / 레이더 표시**는 채널 A/B의 수신 관측을 시각화한다. 재생 시 스캔이 회전하고 새 관측이 도착하는 00:10 이후 10초 간격 등의 시점(일부 보고는 지연 수신)에 표식이 나타난다. 일시정지·시간 이동은 공유 시계를 따르며 중단된 채널은 스캔과 새 표식을 표시하지 않는다. [레이더 표시 설정](data/radar_display.json)의 12초 스캔 주기·1,000m 원·2.5초 표식은 시각화 가정이며 탐지 범위·물리 스캔 모델이 아니다. 표식은 공개 관측의 위치만 사용하며 제작자용 world 데이터나 추정 경로를 사용하지 않는다.

기지는 공유 도면에서 비정형 경계, 평행 유도로와 연결로 7개, 계류장 2개, 지원도로 8개, 울타리 내부 격납고·정비·행정·지원 시설 16개와 외부 고정 폰 2개를 지도와 Godot에 같이 생성한다. [WBDG 공항 계획 자료](https://www.wbdg.org/ffc/dod/unified-facilities-criteria-ufc/ufc-3-260-01)의 일반적 구성 요소를 참고했으며 실제 군 기지의 복제나 설계기준 충족을 의미하지 않는다.

로컬 `LOW_SKY_airfield_reference.docx`는 **전체 반영되지 않았다**. 현재 활주로는 남북 방향 2,500 × 45m이며 문서의 동서 방향 2,750m 배치와 다르다. 강화 항공기 대피호(HAS) 군집, 유류 탱크·방호 둑, 레이더 돔, 북쪽 P1–P10 경보선은 미구현이다. 현재 아치형 건물은 일반 격납고이며 강화 대피호가 아니다. 한국 AIP 공통 기하 분석과 DVIDS 외관 대조도 완료되지 않았으므로 문서가 제안한 설계기준 준수 문구를 구현 사실로 기재하지 않는다.

지도 부지는 **Fictional terrain replacement / 가상 조성 구역**으로 표시한다. 내부 OSM 도로·지형은 불투명한 합성 부지로 대체하고 주변 실제 지도는 유지한다. 낮은 기복의 한국 배경 좌표를 지도·DEM·3D가 공유하며, 실제 토지의 공항 적합성이나 도로 이설을 의미하지 않는다. 3D는 동일 다각형 울타리 + 50m 여유 구역을 평탄화하고 바깥 350m를 DEM으로 연결한다.

기본 지도에는 신선한 수신 탐지가 있는 대상의 마지막 관측 위치만 표시한다. 수신 전·명시적인 미탐지 보고(`detected: false`)·만료된 관측은 지도 표시를 허용하지 않는다. 관측이 끊기면 지도 표식과 3D 라벨을 숨기되, 상세 목록에는 마지막 근거와 시각을 유지한다. **드론 위치 보기**를 켜면 `/api/state?show_positions=1`에서 같은 재생 시각의 실제 시뮬레이션 위치를 별도 필드로 받고, 미탐지 드론도 SIM 표식으로 표시한다. 관측 목록·알림·판단 근거에는 이 위치를 섞지 않는다. 스위치를 끄거나 페이지를 새로고침하면 SIM 레이어가 사라진다. 모든 케이스의 첫 관측은 00:10부터 순차 수신된다. 탐지는 수신된 합성 보고를 기준으로 하며, 회전하는 스윕이나 실제 레이더 성능 계산이 아니다.

## 전체 상황 평가와 피드백 반영

사용자의 상황 평가 에이전트 요구와 공군 측 멘토 피드백을 상세 엔지니어링 리뷰보다 우선했다. [반영 상태](data/references/feedback_adoption.json)에 구현·부분 구현·후속 항목을 기록했다. 원본 피드백 문서는 로컬에만 유지한다. 발표 시나리오는 3개, 부하 시험은 `case_003` 하나이며 **240개 대상은 소프트웨어 부하를 위한 합성 가정**이다.

**전체 상황 평가**는 수신된 근거를 고정해 확인된 사실·불확실성·사용자 검토 사항을 근거 ID와 함께 제공한다. 수동 요청 또는 선택형 자동 평가(재생 중 실제 시간 30초 간격)를 사용한다. 근거 시점을 표시하고 이전 시점임을 구분하며, 새 실행에서는 지난 결과를 숨긴다. 평가는 백그라운드에서 수행해 재생 조작을 막지 않는다. 내보내기에는 보고서와 평가에 사용한 제한된 수신 근거 묶음이 포함된다.

Deep Agents는 관측·출처/센서군 상태·조기 신호·미완료 검토를 읽는 도구 4개를 사용한다. 전체 집계와 최대 12개 항적의 근거 예시를 전달하며 표본임을 명시한다. 숨겨진 위치·경로·미래 수신·만료된 공지·검토자 별칭·자유 입력 사유는 제외한다. 보고서 항목은 제공된 근거 또는 집계 ID를 인용해야 한다. 인용 검증만으로 모델 문장의 사실성을 보장하지는 않는다. 평가 결과가 작전 행동이나 알림 확인을 자동 실행하지 않는다.

기본은 외부 모델 없이 동작하는 **규칙 기반 요약**이다. 실제 LLM을 연결하려면:

```sh
python3 -m venv .local/agent-venv
.local/agent-venv/bin/pip install -r requirements-agent.txt
# 셸에서 LOW_SKY_AGENT_MODEL=provider:model 및 해당 공급자의 인증 정보를 설정한다.
# OpenAI·Anthropic 연동 패키지를 포함하지만 공급자나 모델은 기본 선택하지 않는다.
.local/agent-venv/bin/python tools/monitor_server.py
```

[환경 설정 예시](.env.example)를 참고한다. 서버가 `.env`를 자동으로 읽지는 않는다. 모델을 설정했는데 의존성·인증·연결·출력 검증에 문제가 있으면 실패를 표시하며 규칙 결과를 LLM 성공처럼 보여주지 않는다. 공급자 요청은 20초·재시도 0회, 전체 평가 제한은 60초다. 실제 SDK 도구 호출·구조화 응답은 테스트 모델로 검증했으며, **이 환경에서 인증 정보를 사용한 실제 LLM 호출은 아직 검증하지 않았다**.

## 대량 검토와 가상 센서군

관측 목록을 페이지당 12개로 나누고 전체·근거 결측/상충·현재 근거 미검토 필터를 제공한다. 집계는 전체 수신 대상을 포함한다. 큰 지도에서는 위치 표식을 유지하되 선택한 대상의 경로만 그린다. 미탐지 위치를 보는 SIM 스위치는 기본 꺼짐을 유지한다.

[가상 센서군](data/sensor_fleet_demo.json)은 인원 휴대폰·시설 센서·민간 휴대폰·고정 폰 각 60개, 총 **논리 단말 240개**다. 상태 보고 전용이며 A/B 대상 관측 피드와 3D 외곽 폴 2개와는 별개다. 00:01 첫 상태 수신 후 정상으로 표시하고, 부하 시험에서 01:01 시설 그룹의 단절 보고, 01:10 이후 고정 폰 그룹의 보고 만료, 02:11 복구를 재생한다. 단절 원인은 미확인으로 둔다. 실제 폰 앱·음향 수집·엣지 추론·센서 융합·기관 라우팅·외부 SMS는 후속 범위이며 기존 열린/최소화 PWA의 현재 알림은 유지한다.

대상별 설명은 수신 관측과 출처 상태에서 계산한다. 탐지와 근거 일치, 기종·의도를 분리하며 기종과 의도는 미확인이다. **근거 검토 저장**은 검토자 별칭·판단·사유를 요구하고 변경된 근거 버전의 저장을 거부한다. CLI는 수신 근거 스냅샷·SHA-256 버전·재생 시각·실제 기록 시각을 `.local/track-reviews.jsonl`에 추가하고 디스크 기록 후 성공을 알린다. 여러 실행과 재시작의 기록을 내보낼 수 있다. 이는 로컬 영속 기록이며 인증된 신원이나 변조 방지 저장소는 아니다. 기존 상황 맥락 검토와 알림 확인은 세션 전용이다.

`python3 tools/benchmark_monitor.py --iterations 30`으로 [측정 결과](artifacts/monitor-workload-benchmark.json)를 재현할 수 있다. Python 3.12.11/macOS에서 240개 수신 대상과 240개 가상 단말의 상태 생성+JSON 직렬화 30회를 측정했다. 중앙값 33.82ms, 최대 37.20ms, 응답 1,272,819바이트다. HTTP·브라우저·Godot 렌더·LLM 지연은 제외하며 실제 탐지 정확도를 의미하지 않는다.

## PWA와 현재 알림

모니터는 [웹 앱 매니페스트](monitor/manifest.webmanifest)와 [서비스 워커](monitor/sw.js)를 제공한다. 브라우저가 설치 프롬프트를 제공하면 **Install app / 앱 설치** 버튼을 사용하고, 그렇지 않으면 브라우저의 설치·홈 화면에 추가 메뉴를 사용한다. 설치 지원은 브라우저에 따라 다르다. 알림에는 지원 브라우저, HTTPS 또는 localhost 주소, 브라우저·운영체제 알림 권한이 필요하다.

1. **Enable notifications / 기기 알림 켜기**를 누르고 브라우저 권한을 허용하면 현재 미확인 알림을 한 번 전송한다. 재생 일시정지 중에도 사용할 수 있다.
2. **Notify current alerts / 현재 알림 보내기**로 현재 미확인 알림을 수동 전송할 수 있다. 같은 실행에서 이미 전달한 알림 ID는 중복 전송하지 않는다.
3. 재생 중 새로 수신한 미확인 알림은 갱신 단위로 묶어 보낸다. 최초 로드·시간 이동·새 실행은 기준 상태만 설정하며 과거 알림을 한꺼번에 보내지 않는다.
4. 알림을 누르면 **Current alerts / 현재 알림** 화면을 연다. 자동 확인 처리는 하지 않는다. **Disable notifications / 기기 알림 끄기**는 이 페이지의 발송을 중지하며 브라우저 권한 자체는 철회하지 않는다. 권한은 브라우저 설정에서 변경한다.

전달 이력은 IndexedDB에서 같은 출처·브라우저 프로필의 여러 탭에 걸쳐 동일 실행·알림 ID 중복을 억제한다. 7일이 지난 이력은 다음 전달 시도에서 삭제한다. 이는 알림 중복 방지용이며 감사 기록이 아니다. 알림 사용 선택은 로컬에 저장하며 저장소가 차단되면 유지되지 않을 수 있다.

모니터가 열려 있거나 최소화된 상태에서 폴링이 계속될 때 동작한다. 브라우저·운영체제가 최소화·백그라운드 페이지를 중단할 수 있으므로 제시간 전달은 보장하지 않는다. **서버 푸시, 앱을 닫은 뒤의 전달, 백그라운드 폴링, 오프라인 에셋 캐시, API·OSM 타일 캐시는 구현하지 않는다.** 개발 서버는 loopback에만 연결하므로 휴대폰에서 접근하는 배포가 아니다. 휴대폰에서 쓰려면 별도의 접근 가능한 HTTPS 배포가 필요하다. iOS/iPadOS에서는 홈 화면에 추가한 앱으로 실행해야 알림을 사용할 수 있다. [WebKit의 홈 화면 웹 앱 요구사항](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)을 참고한다. 해당 문서의 Web Push 구독 흐름을 이 프로젝트에서 구현한 것은 아니다.

## 지역 조기 신호와 고정 폰 데모

모니터의 **Area early signals / 지역 조기 신호**는 음향 센서와 시민 앱 제보를 별도 출처로 보여준다. [입력 데이터](data/early_warning_demo.json)는 대표 시나리오 3개와 같은 시계를 사용하는 독립 합성 피드다. 기존 object 트랙의 정체·레이더 탐지 여부와 자동 연결하지 않으며, 실제 주민·휴대폰·음성을 수집하지 않는다. 지도 A/B/C 구역은 실제 주거지 조사 결과가 아니라 가상의 제보 지역이다.

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

우크라이나 [ePPO 개발자 앱 설명](https://play.google.com/store/apps/details?id=ua.quick.brpg.pathfinder)은 시민이 관측한 비행체·소리를 제보하는 방식이다. [미 육군의 음향 센서 사례 소개](https://www.lineofdeparture.army.mil/Journals/Air-Defense-Artillery/ADA-Archive/2024-E-Edition/Mobility-Matters/)에 나오는 Android 기기 포함 설치형 센서와 개인 휴대폰의 자동 감지를 같은 것으로 취급하지 않는다. 이 구현은 시민 제보·설치형 음향 센서·고정 폰의 합성 관측을 구분해 재생한다.

로컬 Sensor Engineering Brief와 Technical Specifications의 관측 상태·시간·불확실성 원칙을 반영했다. 두 원본 DOCX는 수정하거나 공개 저장소에 포함하지 않았다. JSON 변경 후 서버를 재시작하면 입력과 평가가 바뀐다. 새 패키지는 필요 없다.

## 상세 시나리오와 검토 기록

`LOW_SKY_Detailed_Scenario.docx`의 전조·관측 지연·상충·연결 상태 불명·과거 검토 재확인 흐름을 [상황 이벤트](data/situation_review.json)로 반영했다. 원문의 일·시간 단위는 180초 데모로 압축했으며 실제 작전 시간표가 아니다. 케이스는 3개, 부하 시험은 1개로 유지했다. 문서의 공격 순서·무기 선택·교전 권고와 검증되지 않은 성과 수치는 실행 로직에 넣지 않았다.

**Situation & human review / 상황과 검토**를 펼치면 현재까지 수신된 맥락과 불확실성을 보고, 근거를 선택해 확인·추가 검토·기각 의견을 저장할 수 있다. 기록에는 사건, 근거, 당시 설명, 불확실성, 판단, 사유, 재생 시각의 7개 항목이 들어간다. 02:30의 재검토 사건은 같은 실행에서 사용자가 실제로 저장한 이전 기록을 연결한다. 결과 수는 실제 입력한 기록에서 계산하며 정확도는 산출하지 않는다. 시간 이동·초기화·케이스 변경은 새 실행으로 처리하고, 서버 재시작 시 메모리 기록은 사라진다.

[우크라이나 관측 교훈과 출처](data/references/ukraine_observation_lessons.json)는 공개 분석의 정성적 내용을 불확실성 설명에 연결한다. CSIS의 디코이 혼재 분석, RUSI의 전자전 분석, CSIS의 통신 방식 관련 분석을 참고했다. 단일 관측으로 기체 역할을 단정하거나, RF 신호 부재로 광섬유 사용을 확정하지 않는다. 합성 대상 수·경로·점수는 이 자료에서 추정한 전술 모델이 아니다.

## 고정 폰 시범 구역과 기지 표현

커뮤니티 A/B/C와 별도로 **Fixed-phone pilot / 고정 폰 시범 구역**을 추가했다. 가상 기지 울타리 바깥에 3m 폴 2개와 폰 함체를 배치하고 지도 설치 지점과 Godot 모델 좌표를 일치시켰다. 공유 `field_installations`의 로컬 X/Z 좌표는 `(1000, 100)`, `(1000, 200)`이며 각 폴의 밑면은 해당 지점의 지형 높이에 맞춘다. 표시 구역은 `(1000, 150)`을 중심으로 반경 100m이며 탐지 범위가 아니다. 하드웨어·방수 등급·탐지 성능은 미선정·미검증이다.

- 00:00: 전원·통신 정상 및 후보 미보고 합성 관측.
- 01:30: 첫 폰 후보 관측 수신. 01:35에 두 번째 폰의 지연 관측 수신.
- 02:00: 게이트웨이가 보고한 통신 단절·배터리 상태. 후보 없음과 구별한다.
- 02:30: 전원·통신 복구와 후보 미보고 관측.

카드에는 **마지막 수신 보고**의 전원·통신 상태와 관측 유효성을 함께 표시한다. 실제 폰 앱, 음성 수집, 장애 진단, 설치 배선은 구현하지 않았다. [민수용 스펙 카탈로그](data/sensors/civilian_reference_specs.json)에 전용 `pole_phone_reference` 프로필을 추가했다.

기지에는 아치형 격납고 2개, 사무·정비·지원 시설 외형과 지원 건물 3개를 보강했다. 울타리 내부 시설 16개, 외부 고정 폰 2개와 일반 구역명 5개를 공유 배치 데이터에서 지도·3D에 표시한다. 활주로 2,500×45m와 부지 경계는 유지했다. 상세 문서와 보조 배치 문서의 일반적인 건축 표현을 반영한 가상 장면이며 특정 기지나 설계 표준 준수를 주장하지 않는다.

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

공유 시계·드론 따라보기 검증은 별도 서버에서 실행하면 사용 중인 재생에 영향을 주지 않는다.

```sh
# 테스트 전용 터미널:
python3 tools/monitor_server.py --port 8766
# 다른 터미널:
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script res://tools/verify_monitor.gd --quit-after 1200 -- --monitor --monitor-port=8766
```

창을 표시하는 검증 명령은 실제 GUI 입력 경로에서 패닝·회전·버튼 클릭의 공존도 검사한다. Headless 실행에서는 렌더링이 필요한 GUI 버튼 전달 검사만 건너뛴다.

마지막 명령은 한국 DEM 장면을 렌더링해 `artifacts/korea-preview.png`를 저장하고 종료한다. `--capture --overview`는 전체 조망을 `artifacts/korea-overview.png`에 저장한다. `--plains`는 `plains-*` 파일로 저장한다. `--hills`를 추가하면 기존 지형을 `artifacts/asset-preview.png` 또는 `artifacts/asset-overview.png`에 저장한다. 그래픽 장치가 필요하다. 자동 검증과 실제 렌더 확인은 에셋 연결의 증거이며, 완성된 에이전트 시스템의 검증을 의미하지 않는다. 알림 단위 테스트만으로 모든 플랫폼의 운영체제 알림 표시까지 검증되었다고 볼 수는 없다.

## 3D 품질과 출처

외부 모델의 품질과 실제 장소의 재현 정확도는 별도 항목이다. 외부 모델은 형태·재질의 완성도를 높이는 데 활용하고, 크기·피벗·배치는 장면에서 맞춘다. 상세 모델을 쓰더라도 실제 장소를 실측한 것처럼 표시하지 않는다.

현재 반입한 [Kenney City Kit Industrial](https://kenney.nl/assets/city-kit-industrial)은 CC0 스타일화 모델이며 실사 모델이 아니다. 정확한 출처, 파일 해시, 수정 여부는 `godot/third_party/kenney_industrial/provenance.json`에 보관했다. 격납고로 사용하는 건물도 가상 장면용 대체 모델이다.

현재 [Poly Haven](https://polyhaven.com/license)의 CC0 PBR 재질 4세트(콘크리트·금속·아스팔트·초지)와 HDRI를 적용했다. [Cesium 항공기 샘플](https://github.com/CesiumGS/cesium/tree/main/Apps/SampleData/models/CesiumAir)은 원본 라이선스를 함께 보관하며 장면용으로 크기만 정규화했다. 모든 외부 원본 파일은 변경하지 않았고 재질 배율·색상은 Godot에서 조절한다. 출처는 `godot/third_party/realistic/provenance.json`에 있다.

지도는 [OpenStreetMap](https://www.openstreetmap.org/copyright)을 배경으로 사용한다. 한국 중부의 임의 기준점 36.23N, 127.08E에 가상 기지를 겹쳐 그린다. 실제 시설 위치나 해당 토지의 용도를 뜻하지 않는다. [배치 검토 기록](data/terrain/site_placement.json)의 동일한 100m 샘플 비교에서 부지 외접 영역의 자연 고도 차는 기존 약 367m에서 약 31m로 줄었다. OSM 주변 평야를 참고했으나 내부 농로·필지는 가상 조성으로 대체한다. 경계는 측량 필지 경계가 아니며 도로·하천·홍수·풍향·토지 이용 적합성을 전수 검증한 건설 후보지가 아니다. `monitor/map_config.json`에서 기준점을 관리하며, 변경 시 고도 데이터를 함께 재생성해야 한다. X는 동쪽, Z는 남쪽이다. 소규모 영역에 대한 구면 근사로 지도에 투영하므로 측량용 좌표 변환은 아니다.

OSM 타일은 브라우저에 보이는 영역만 요청하며 attribution을 표시한다. 일괄 수집·오프라인 저장을 하지 않는다. [타일 사용 정책](https://operations.osmfoundation.org/policies/tiles/)을 따른다. 자동 UI 검증에는 `?tiles=off`를 사용한다. 기지 평면도와 3D는 타일 네트워크 없이 동작한다. Google Maps/Earth 자료는 사용하지 않는다.

3D 지형은 [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/)의 N36E127 HGT를 bilinear 보간해 만들었다. 원본 체크섬, 출처, 처리 방법은 `data/terrain/`에 기록했다. 지형 원본 격자는 1각초이며 표시 격자는 50m다. 기준점 고도 5m를 로컬 Y=0으로 삼으며 수직 과장은 없다. **가상 기지와 주변 350m 전이 구간은 평탄화·보간으로 수정했다.** 이 부분은 실제 지형 재현이 아니다. 나머지 주변 지형은 DEM의 상대 고도를 사용한다. 위성사진·실제 건물·식생 분포는 반입하지 않아 텍스처는 예시 재질이다.

이전 우크라이나 참고 방향의 합성 평야 프리셋은 비교 모드로 남겨 두었다. 기본 지역은 이후 사용자 선택에 따라 한국으로 변경했다.

`LOW_SKY_scenario_v2.docx`와 `LOW_SKY_Detailed_Scenario.docx`는 로컬 기획 참고 문서다. 원본은 공개 저장소에서 제외한다. 현재 실행 데이터는 대표 상황 2개와 부하 시험 1개로 축약한 합성 관측 시나리오다. 공개 전조·센서 상태·불확실성은 별도 상황 이벤트와 검토 기록으로 제공한다. 문서에서 언급한 `sim/raid.py`, `core/classify.py`는 이 저장소의 기존 구현이 아니다. v2의 전체 시나리오나 무기 선택·교전 권고는 구현하지 않았다.
