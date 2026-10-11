extends Node3D
## User-positioned scene personnel and sensors. Positions come only from the shared state.

const Detailed = preload("res://detailed_environment.gd")
# Display assumptions only (not detection ranges); state unit_kinds take precedence.
const FALLBACK_RANGES = {"infantry": 0, "radar": 5000, "detection_phone": 1500, "effector_team": 2500}
const RING_COLORS = {"radar": Color(0.35, 0.9, 1.0, 0.55), "detection_phone": Color(1.0, 0.75, 0.25, 0.55), "effector_team": Color(1.0, 0.5, 0.2, 0.55)}
const LABEL_HEIGHTS = {"infantry": 2.6, "radar": 4.4, "detection_phone": 3.8, "effector_team": 4.0}
const PIN_COLORS = {"infantry": "62c7b3", "radar": "6fd8ec", "detection_phone": "e8b65a", "effector_team": "e8875a"}
const FALLBACK_KO = {"infantry": "보병", "radar": "레이더", "detection_phone": "드론 청음 초소", "effector_team": "대응 팀"}
var units: Dictionary = {}
## Set by the preview so acoustic listening posts share the scene's site materials.
var materials: Dictionary = {}

static func material(color: String) -> StandardMaterial3D:
	var result = StandardMaterial3D.new()
	result.albedo_color = Color(color)
	result.roughness = 0.9
	return result

static func add_marker(root: Node3D, pin_size: float, pin_color: String, label_height: float) -> void:
	# A ground diamond makes the exact position legible without changing body scale.
	var pin = Detailed.box(root, Vector3(pin_size, 0.025, pin_size), Vector3(0, 0.15, 0), material(pin_color))
	pin.rotation.y = PI / 4.0
	var label = Label3D.new()
	label.name = "UnitLabel"
	label.position.y = label_height
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.fixed_size = true
	label.no_depth_test = true
	label.font_size = 24
	label.pixel_size = 0.0011
	label.modulate = Color("9aefda")
	label.outline_size = 6
	root.add_child(label)

static func make_person(with_marker: bool = true) -> Node3D:
	var person = Node3D.new()
	var uniform = material("586653")
	var equipment = material("333f37")
	var boots = material("242928")
	var skin = material("cba98a")
	# Neutral standing pose, with no target, engagement or weapon animation.
	Detailed.box(person, Vector3(0.48, 0.58, 0.27), Vector3(0, 1.15, 0), uniform)
	Detailed.box(person, Vector3(0.43, 0.43, 0.12), Vector3(0, 1.19, -0.17), equipment)
	Detailed.box(person, Vector3(0.34, 0.42, 0.17), Vector3(0, 1.18, 0.20), equipment)
	Detailed.box(person, Vector3(0.43, 0.22, 0.24), Vector3(0, 0.80, 0), uniform)
	for side in [-1, 1]:
		Detailed.box(person, Vector3(0.17, 0.60, 0.19), Vector3(side * 0.14, 0.46, 0), uniform)
		Detailed.box(person, Vector3(0.20, 0.16, 0.32), Vector3(side * 0.14, 0.08, -0.05), boots)
		var arm = Detailed.box(person, Vector3(0.15, 0.48, 0.18), Vector3(side * 0.34, 1.12, 0), uniform)
		arm.rotation.z = side * 0.10
		Detailed.box(person, Vector3(0.13, 0.17, 0.14), Vector3(side * 0.37, 0.81, 0), skin)
	Detailed.box(person, Vector3(0.27, 0.29, 0.25), Vector3(0, 1.58, -0.015), skin)
	Detailed.box(person, Vector3(0.34, 0.17, 0.33), Vector3(0, 1.77, 0), uniform)
	Detailed.box(person, Vector3(0.39, 0.05, 0.39), Vector3(0, 1.70, -0.02), equipment)
	if with_marker:
		add_marker(person, 1.1, PIN_COLORS.infantry, LABEL_HEIGHTS.infantry)
	return person

static func make_radar() -> Node3D:
	# Generic small FMCW counter-UAS radar on a tripod; no specific product.
	var root = Node3D.new()
	var green = material("3f4a3c")
	var grey = material("5d6461")
	var dark = material("262b28")
	for index in range(3):
		var angle = TAU * index / 3.0
		var foot = Vector3(cos(angle) * 1.25, 0.04, sin(angle) * 1.25)
		Detailed.rod(root, Vector3(0, 1.05, 0), foot, 0.035, dark)
		Detailed.box(root, Vector3(0.18, 0.05, 0.18), foot, dark)
	Detailed.box(root, Vector3(0.26, 0.22, 0.26), Vector3(0, 1.05, 0), grey)
	Detailed.rod(root, Vector3(0, 1.1, 0), Vector3(0, 3.0, 0), 0.05, grey)
	Detailed.box(root, Vector3(0.34, 0.24, 0.34), Vector3(0, 3.08, 0), dark)
	# Back-to-back flat antenna panels, slightly tilted up.
	for side in [-1, 1]:
		var panel = Detailed.box(root, Vector3(0.95, 0.62, 0.08), Vector3(0, 3.55, side * 0.09), green)
		panel.rotation.x = side * -0.12
		var face = Detailed.box(root, Vector3(0.8, 0.48, 0.015), Vector3(0, 3.55, side * 0.14), grey)
		face.rotation.x = side * -0.12
	# Ground electronics case and cable.
	Detailed.box(root, Vector3(0.6, 0.35, 0.4), Vector3(0.9, 0.18, 0.9), green)
	Detailed.rod(root, Vector3(0.75, 0.3, 0.75), Vector3(0.05, 1.0, 0.05), 0.015, dark)
	return root

static func make_effector_team() -> Node3D:
	# Generic light vehicle with a pedestal launch rail; not a specific weapon system.
	var root = Node3D.new()
	var olive = material("4d5233")
	var dark_olive = material("363a24")
	var tyre = material("1f2220")
	var glass = material("2a3a40")
	Detailed.box(root, Vector3(1.9, 0.55, 4.6), Vector3(0, 0.78, 0), olive)
	Detailed.box(root, Vector3(1.85, 0.85, 1.6), Vector3(0, 1.48, 1.25), olive)
	Detailed.box(root, Vector3(1.6, 0.5, 0.04), Vector3(0, 1.55, 2.06), glass)
	Detailed.box(root, Vector3(1.9, 0.35, 0.08), Vector3(0, 1.2, -2.27), dark_olive)
	for side in [-1, 1]:
		Detailed.box(root, Vector3(0.08, 0.35, 2.7), Vector3(side * 0.91, 1.2, -0.9), dark_olive)
		for z in [-1.5, 1.4]:
			Detailed.rod(root, Vector3(side * 0.82, 0.42, z), Vector3(side * 1.08, 0.42, z), 0.42, tyre)
	# Pedestal with a tilted tube rail, parked in a neutral stowed elevation.
	Detailed.rod(root, Vector3(0, 1.05, -1.0), Vector3(0, 1.7, -1.0), 0.14, dark_olive)
	Detailed.box(root, Vector3(0.7, 0.18, 0.7), Vector3(0, 1.78, -1.0), dark_olive)
	for side in [-1, 1]:
		Detailed.rod(root, Vector3(side * 0.16, 1.85, -1.75), Vector3(side * 0.16, 2.35, -0.15), 0.11, olive)
	for side in [-1, 1]:
		var figure = make_person(false)
		figure.position = Vector3(side * 1.75, 0, 0.6 - side * 0.5)
		figure.rotation.y = side * 0.4
		root.add_child(figure)
	return root

static func fallback_materials() -> Dictionary:
	return {"concrete": material("8a8d88"), "metal": material("7b858e"), "dark_metal": material("333b3c"), "painted_metal": material("879594"), "glass": material("233e47")}

static func make_range_ring(radius: float, color: Color) -> MeshInstance3D:
	var ring = MeshInstance3D.new()
	ring.name = "RangeRing"
	var mesh = TorusMesh.new()
	mesh.inner_radius = radius - 1.0
	mesh.outer_radius = radius + 1.0
	mesh.rings = 192
	mesh.ring_segments = 6
	ring.mesh = mesh
	var ring_material = StandardMaterial3D.new()
	ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ring_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	ring_material.albedo_color = color
	ring.material_override = ring_material
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ring.position.y = 0.5
	ring.set_meta("range_m", radius)
	return ring

func make_unit(kind: String) -> Node3D:
	if kind == "infantry":
		return make_person()
	var root: Node3D
	match kind:
		"radar":
			root = make_radar()
		"detection_phone":
			# Drone acoustic listening post: the site's phone pole plus a small microphone.
			var pole_materials = fallback_materials() if materials.is_empty() else materials
			root = Detailed.make_phone_sensor_pole(pole_materials)
			add_microphone(root, pole_materials)
		"effector_team":
			root = make_effector_team()
	add_marker(root, 1.6 if kind == "effector_team" else 1.1, PIN_COLORS[kind], LABEL_HEIGHTS[kind])
	return root

static func add_microphone(root: Node3D, m: Dictionary) -> void:
	# Short boom with a foam windscreen, kept below the 3 m pole top.
	Detailed.rod(root, Vector3(0, 2.45, 0.04), Vector3(0.22, 2.55, 0.18), 0.012, m.dark_metal)
	var windscreen = MeshInstance3D.new()
	windscreen.name = "MicrophoneWindscreen"
	var sphere = SphereMesh.new()
	sphere.radius = 0.055
	sphere.height = 0.14
	windscreen.mesh = sphere
	windscreen.material_override = material("2b2f2e")
	windscreen.position = Vector3(0.24, 2.56, 0.2)
	root.add_child(windscreen)

func sync(rows: Array, ground_height: Callable, kinds: Array = []) -> void:
	var ranges: Dictionary = FALLBACK_RANGES.duplicate()
	var kind_ko: Dictionary = FALLBACK_KO.duplicate()
	for kind in kinds:
		if kind is Dictionary and FALLBACK_RANGES.has(str(kind.get("id", ""))):
			if kind.get("display_range_m") is float or kind.get("display_range_m") is int:
				ranges[str(kind.id)] = float(kind.display_range_m)
			if kind.get("label") is Dictionary and kind.label.has("ko"):
				kind_ko[str(kind.id)] = str(kind.label.ko)
	var present: Dictionary = {}
	for row in rows:
		if not row is Dictionary or not FALLBACK_RANGES.has(str(row.get("kind", ""))) or not row.has_all(["id", "position"]):
			continue
		var position = row.position
		if not position is Array or position.size() != 3:
			continue
		var id = str(row.id)
		var kind = str(row.kind)
		present[id] = true
		if units.has(id) and units[id].get_meta("kind") != kind:
			remove_child(units[id])
			units[id].queue_free()
			units.erase(id)
		if not units.has(id):
			var created = make_unit(kind)
			created.set_meta("unit_id", id)
			created.set_meta("kind", kind)
			add_child(created)
			units[id] = created
		var unit: Node3D = units[id]
		var supplied = Vector3(float(position[0]), 0, float(position[2]))
		if not unit.has_meta("supplied_position") or unit.get_meta("supplied_position") != supplied:
			unit.set_meta("supplied_position", supplied)
			unit.position = supplied + Vector3(0, float(ground_height.call(supplied.x, supplied.z)), 0)
		unit.set_meta("status", str(row.get("status", "positioned")))
		sync_ring(unit, kind, float(ranges[kind]))
		var label = row.get("label", {})
		if not label is Dictionary:
			label = {}
		unit.get_node("UnitLabel").text = "%s / %s" % [label.get("en", id), label.get("ko", kind_ko[kind])]
	for id in units.keys():
		if not present.has(id):
			remove_child(units[id])
			units[id].queue_free()
			units.erase(id)

func sync_ring(unit: Node3D, kind: String, radius: float) -> void:
	var ring = unit.get_node_or_null("RangeRing")
	if ring and (radius <= 0 or ring.get_meta("range_m") != radius):
		unit.remove_child(ring)
		ring.queue_free()
		ring = null
	if ring == null and radius > 0 and RING_COLORS.has(kind):
		unit.add_child(make_range_ring(radius, RING_COLORS[kind]))

func reground(ground_height: Callable) -> void:
	for unit in units.values():
		var supplied: Vector3 = unit.get_meta("supplied_position")
		unit.position = supplied + Vector3(0, float(ground_height.call(supplied.x, supplied.z)), 0)
