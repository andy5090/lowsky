extends RefCounted
## English / Korean strings for the 3D view. The language follows the web monitor
## (ui_language in /api/state); standalone runs and unknown values stay English.

const LANGUAGES = ["en", "ko"]
static var language = "en"

const STRINGS = {
	"panel.collapse": {"en": "Collapse controls", "ko": "패널 접기"},
	"panel.expand": {"en": "Expand controls", "ko": "패널 펼치기"},
	"subtitle.author": {"en": "AUTHOR VIEW\nFull scene context", "ko": "작성자 시점\n전체 장면"},
	"subtitle.assets": {"en": "ASSET STUDY · AUTHOR VIEW\nBuilding samples + procedural placeholders", "ko": "에셋 검토 · 작성자 시점\n건물 샘플 + 절차 생성 임시 모델"},
	"terrain.dem": {"en": "Terrain: Gyeonggi DEM  [T]", "ko": "지형: 경기 DEM  [T]"},
	"terrain.plains": {"en": "Terrain: Plains  [T]", "ko": "지형: 평지  [T]"},
	"terrain.hills": {"en": "Terrain: Hills  [T]", "ko": "지형: 구릉  [T]"},
	"case.consistent": {"en": "Consistent", "ko": "일치"},
	"case.conflicting": {"en": "Conflicting", "ko": "충돌"},
	"case.missing": {"en": "Missing", "ko": "결측"},
	"playback": {"en": "Pause / Resume  [Space]", "ko": "일시정지 / 재개  [Space]"},
	"follow.start": {"en": "Follow selected drone  [F]", "ko": "선택 드론 추적  [F]"},
	"follow.stop": {"en": "Return to overview  [F]", "ko": "전체 보기로 복귀  [F]"},
	"drone.previous": {"en": "Previous drone  [", "ko": "이전 드론  ["},
	"drone.next": {"en": "Next drone  ]", "ko": "다음 드론  ]"},
	"camera.none": {"en": "CAMERA: No drones", "ko": "카메라: 드론 없음"},
	"camera.selected": {"en": "CAMERA: %s  (%d / %d)\n%s · %s m display span", "ko": "카메라: %s  (%d / %d)\n%s · 표시 폭 %s m"},
	"approach": {"en": "Approach view  [B]", "ko": "접근 경로 보기  [B]"},
	"positions.toggle": {"en": "Show all drones (author view)", "ko": "전체 드론 표시 (작성자 시점)"},
	"time.clock": {"en": "%s  |  %03d / %03d s", "ko": "%s  |  %03d / %03d 초"},
	"time.counts": {"en": "  |  Objects %d · Detected labels %d", "ko": "  |  비행체 %d · 탐지 %d"},
	"time.seed": {"en": "  |  Seed %s", "ko": "  |  시드 %s"},
	"source.online": {"en": "online", "ko": "정상"},
	"source.offline": {"en": "offline", "ko": "중단"},
	"source.stale": {"en": "stale", "ko": "오래된 기록"},
	"source.unknown": {"en": "unknown", "ko": "미확인"},
	"monitor.connected": {"en": "MONITOR: connected", "ko": "모니터링: 연결됨"},
	"monitor.disconnected": {"en": "MONITOR: disconnected · replay frozen", "ko": "모니터링: 연결 끊김 · 재생 정지"},
	"hint.standalone": {"en": "Left / Middle drag: pan\nRight / Shift+Left drag: orbit\nWheel: zoom   C: view   H: home   B: approach\n1 / 2 / 3: branch   R: restart\n[ / ]: previous / next drone   F: follow / overview\nSynthetic observations. No LLM connected.",
		"ko": "왼쪽·가운데 드래그: 이동\n오른쪽·Shift+왼쪽 드래그: 회전\n휠: 확대·축소   C: 시점   H: 기본 위치   B: 접근 경로\n1 / 2 / 3: 사례 전환   R: 처음부터\n[ / ]: 이전·다음 드론   F: 추적·전체 보기\n합성 관측 자료입니다. LLM은 연결되지 않았습니다."},
	"hint.monitor": {"en": "Left / Middle: pan   Right: orbit\nWheel: zoom   C: view   H: home   B: approach\nReplay control: %s\nLabels: received detections / author view\n[ / ]: previous / next drone   F: follow / overview\nCamera selection: author view",
		"ko": "왼쪽·가운데: 이동   오른쪽: 회전\n휠: 확대·축소   C: 시점   H: 기본 위치   B: 접근 경로\n재생 제어: %s\n라벨: 수신 탐지 / 작성자 시점\n[ / ]: 이전·다음 드론   F: 추적·전체 보기\n카메라 선택: 작성자 시점"},
	"hint.altitude": {"en": "\nIllustrative altitude\nBeyond local DEM: schematic space", "ko": "\n표시용 고도\n지역 DEM 범위 밖: 개략 공간"},
	"label.author": {"en": "AUTHOR ", "ko": "가상 "},
	"label.detected": {"en": "DETECTED ", "ko": "탐지 "},
	"label.sim": {"en": "SIM ", "ko": "가상 "},
	"tactics.allocated": {"en": "ALLOCATED: %s (training record)", "ko": "할당: %s (훈련 기록)"},
	"lean.decoy_leaning": {"en": "DECOY LEANING", "ko": "미끼 성향"},
	"lean.attack_leaning": {"en": "ATTACK LEANING", "ko": "공격 성향"},
	"lean.reconnaissance_leaning": {"en": "RECONNAISSANCE LEANING", "ko": "정찰 성향"},
	"lean.indeterminate": {"en": "INDETERMINATE", "ko": "분리 불가"},
	"lean.insufficient_data": {"en": "INSUFFICIENT DATA", "ko": "자료 부족"},
	"profile.jet": {"en": "JET", "ko": "제트"},
	"profile.multirotor": {"en": "MULTIROTOR", "ko": "멀티로터"},
	"profile.light_airframe": {"en": "LIGHT AIRFRAME", "ko": "경량 기체"},
	"profile.fixed_wing": {"en": "FIXED WING", "ko": "고정익"},
	"asset.available": {"en": "AVAILABLE", "ko": "사용 가능"},
	"asset.restricted": {"en": "RESTRICTED", "ko": "사용 제한"},
	"asset.unavailable": {"en": "UNAVAILABLE", "ko": "사용 불가"},
	"selection.applied": {"en": "APPLIED", "ko": "적용됨"},
	"selection.pending": {"en": "PENDING", "ko": "적용 대기"},
	"mission.finale": {"en": "DESCENT", "ko": "하강"},
	"mission.complete": {"en": "FACILITY DAMAGE", "ko": "시설 피해"},
	"mission.partial": {"en": "RESTRICTED", "ko": "제한 운영"},
	"mission.prevented": {"en": "FACILITY CLEAR", "ko": "시설 정상"},
	"geo.launch": {"en": "Launch area\n· %s", "ko": "발진 구역\n· %s"},
	"airframe.quadcopter": {"en": "Quadcopter", "ko": "쿼드콥터"},
	"airframe.fpv": {"en": "FPV quad", "ko": "FPV 쿼드콥터"},
	"airframe.hexacopter": {"en": "Hexacopter", "ko": "헥사콥터"},
	"airframe.geran_2": {"en": "Geran-2 / Shahed-136", "ko": "Geran-2(Shahed-136)"},
	"airframe.geran_3": {"en": "Geran-3 / jet delta", "ko": "Geran-3 · 제트 델타익"},
	"airframe.lancet": {"en": "Lancet / tandem X", "ko": "Lancet · 탠덤 X형 날개"},
	"airframe.garpiya": {"en": "Garpiya / delta", "ko": "Garpiya · 델타익"},
	"airframe.orlan_10": {"en": "Orlan-10 / fixed wing", "ko": "Orlan-10 · 고정익"},
	"airframe.orlan_30": {"en": "Orlan-30 / fixed wing", "ko": "Orlan-30 · 고정익"},
	"airframe.zala": {"en": "ZALA / flying wing", "ko": "ZALA · 전익기"},
	"airframe.supercam": {"en": "Supercam / flying wing", "ko": "Supercam · 전익기"},
	"airframe.gerbera": {"en": "Gerbera / light delta", "ko": "Gerbera · 경량 델타익"},
	"airframe.parodiya": {"en": "Parodiya / light fixed wing", "ko": "Parodiya · 경량 고정익"},
	"airframe.molniya": {"en": "Molniya / twin boom", "ko": "Molniya · 쌍동체"},
	"desktop.monitor": {"en": "Monitoring [F6]", "ko": "모니터링 [F6]"},
	"desktop.monitor_tip": {"en": "Return to monitoring [F6]", "ko": "모니터링 화면으로 전환 [F6]"},
	"desktop.fullscreen": {"en": "Fullscreen [F11]", "ko": "전체 화면 [F11]"},
	"desktop.fullscreen_tip": {"en": "Toggle full screen [F11]", "ko": "전체 화면 전환 [F11]"},
	"desktop.connecting": {"en": "Connecting window controls…", "ko": "창 제어 연결 중…"},
	"desktop.request_failed": {"en": "Window controls unavailable", "ko": "창 제어 연결 실패"},
	"desktop.unavailable": {"en": "Window controls unavailable", "ko": "창 제어 사용 불가"},
	"desktop.command_failed": {"en": "Window command failed", "ko": "창 제어 요청 실패"},
	"desktop.disconnected": {"en": "Window controls disconnected; retrying", "ko": "창 제어 연결 끊김 · 재연결 중"},
	"desktop.rejected": {"en": "Window command rejected (%s)", "ko": "창 제어 요청 거절 (%s)"},
	"desktop.invalid": {"en": "Invalid window state", "ko": "창 제어 응답 오류"},
	"desktop.error": {"en": "Window control: %s", "ko": "창 제어: %s"},
	"desktop.switching": {"en": "Switching window…", "ko": "창 전환 중…"},
	"desktop.ready": {"en": "F6 · Monitoring    F11 · Fullscreen", "ko": "F6 · 모니터링    F11 · 전체 화면"},
}

## Returns true when a supported language was supplied and differs from the current one.
static func set_language(value) -> bool:
	if not value is String or not value in LANGUAGES or value == language:
		return false
	language = value
	return true

static func has(key: String) -> bool:
	return STRINGS.has(key)

static func t(key: String, values: Array = []) -> String:
	var entry: Dictionary = STRINGS[key]
	var text = str(entry.get(language, entry.en))
	return text if values.is_empty() else text % values

## Picks the current language from supplied en/ko data, falling back to English.
static func pick(pair, fallback: String = "") -> String:
	if not pair is Dictionary:
		return fallback
	return str(pair.get(language, pair.get("en", fallback)))
