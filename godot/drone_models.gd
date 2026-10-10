extends RefCounted
## Recognizable visual approximations; dimensions are display proportions, not specifications.
## All noses point toward -Z. Cached PackedScenes share merged geometry and materials.

static var _scenes: Dictionary = {}
static var _materials: Dictionary = {}

static func make(airframe_id: String) -> Node3D:
	if not _scenes.has(airframe_id):
		var model := Node3D.new()
		model.name = airframe_id
		model.set_meta("rotors", [])
		if airframe_id == "fpv":
			_fpv(model)
		elif airframe_id in ["quadcopter", "hexacopter"]:
			_multirotor(model, airframe_id == "hexacopter")
		else:
			_fixed_wing(model, airframe_id)
		_merge_static(model)
		# Node metadata references are rebuilt after instancing the packed scene.
		model.remove_meta("rotors")
		var scene := PackedScene.new()
		for child in model.get_children():
			child.owner = model
			for grandchild in child.get_children():
				grandchild.owner = model
		scene.pack(model)
		_scenes[airframe_id] = scene
		model.free()
	var result: Node3D = _scenes[airframe_id].instantiate()
	var rotors: Array = []
	for child in result.get_children():
		if child.has_meta("axis"):
			rotors.append(child)
	result.set_meta("rotors", rotors)
	return result

static func _mat(key: String) -> StandardMaterial3D:
	if _materials.has(key):
		return _materials[key]
	var material := StandardMaterial3D.new()
	var colors := {"paint": Color("c3c5be"), "white": Color("dddcd2"),
		"olive": Color("727667"), "carbon": Color("252a2b"), "rubber": Color("161a1c"),
		"metal": Color("717b80"), "glass": Color("253f4c"), "seam": Color("737a77"),
		"red": Color("aa3b2b"), "green": Color("4d856b")}
	material.albedo_color = colors.get(key, Color.WHITE)
	material.roughness = 0.65
	if key == "metal":
		material.metallic = 0.75
		material.roughness = 0.3
	elif key == "glass":
		material.metallic = 0.35
		material.roughness = 0.16
	elif key == "rubber" or key == "carbon":
		material.roughness = 0.87
	_materials[key] = material
	return material

static func _mesh(parent: Node3D, mesh: Mesh, position: Vector3, material: String) -> MeshInstance3D:
	var part := MeshInstance3D.new()
	part.mesh = mesh
	part.position = position
	part.material_override = _mat(material)
	parent.add_child(part)
	return part

static func _ellipsoid(parent: Node3D, position: Vector3, size: Vector3, material: String) -> MeshInstance3D:
	var sphere := SphereMesh.new()
	sphere.radius = 0.5
	sphere.height = 1.0
	sphere.radial_segments = 16
	sphere.rings = 8
	var part := _mesh(parent, sphere, position, material)
	part.scale = size
	return part

static func _rod(parent: Node3D, a: Vector3, b: Vector3, radius: float, material: String, tip_radius: float = -1.0) -> MeshInstance3D:
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = radius if tip_radius < 0.0 else tip_radius
	cylinder.bottom_radius = radius
	cylinder.height = a.distance_to(b)
	cylinder.radial_segments = 12
	var part := _mesh(parent, cylinder, (a + b) * 0.5, material)
	var direction := (b - a).normalized()
	var reference := Vector3.FORWARD if absf(direction.dot(Vector3.FORWARD)) < 0.95 else Vector3.RIGHT
	var right := direction.cross(reference).normalized()
	part.basis = Basis(right, direction, right.cross(direction).normalized())
	return part

static func _box(parent: Node3D, position: Vector3, size: Vector3, material: String) -> MeshInstance3D:
	var box := BoxMesh.new()
	box.size = size
	return _mesh(parent, box, position, material)

static func _triangle(surface: SurfaceTool, a: Vector3, b: Vector3, c: Vector3) -> void:
	# Godot front faces use clockwise winding.
	surface.add_vertex(a)
	surface.add_vertex(c)
	surface.add_vertex(b)

static func _loft(parent: Node3D, rings: Array, material: String) -> MeshInstance3D:
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	surface.set_smooth_group(0)
	var count: int = rings[0].size()
	for r in range(rings.size() - 1):
		for i in range(count):
			var j := (i + 1) % count
			_triangle(surface, rings[r][i], rings[r + 1][j], rings[r + 1][i])
			_triangle(surface, rings[r][i], rings[r][j], rings[r + 1][j])
	for i in range(1, count - 1):
		_triangle(surface, rings[0][0], rings[0][i + 1], rings[0][i])
		_triangle(surface, rings[-1][0], rings[-1][i], rings[-1][i + 1])
	surface.index()
	surface.generate_normals()
	return _mesh(parent, surface.commit(), Vector3.ZERO, material)

static func _body(parent: Node3D, center: Vector3, length: float, width: float, height: float, material: String) -> void:
	var rings: Array = []
	for section in [Vector2(-0.5, 0.03), Vector2(-0.44, 0.48), Vector2(-0.29, 0.9),
		Vector2(-0.06, 1.0), Vector2(0.25, 0.8), Vector2(0.46, 0.35), Vector2(0.5, 0.16)]:
		var ring: Array[Vector3] = []
		for i in range(16):
			var angle := TAU * i / 16.0
			ring.append(center + Vector3(cos(angle) * width * section.y * 0.5,
				sin(angle) * height * section.y * 0.5, section.x * length))
		rings.append(ring)
	_loft(parent, rings, material)

## Each wing has an actual rounded leading edge and a thin trailing edge.
static func _wing(parent: Node3D, span: float, chord: float, tip_chord: float, sweep: float, z: float, y: float, material: String, dihedral: float = 0.025) -> void:
	for side in [-1.0, 1.0]:
		var rings: Array = []
		for fraction in [0.0, 0.6, 1.0]:
			var local_chord := lerpf(chord, tip_chord, fraction)
			var leading: float = z + sweep * fraction
			var thickness := local_chord * 0.095
			var ring: Array[Vector3] = []
			for point in [Vector2(0, 0), Vector2(0.08, 0.7), Vector2(0.28, 1),
				Vector2(0.65, 0.55), Vector2(1, 0), Vector2(0.65, -0.22),
				Vector2(0.28, -0.35), Vector2(0.08, -0.25)]:
				ring.append(Vector3(span * 0.5 * fraction * side,
					y + span * fraction * dihedral + point.y * thickness,
					leading + point.x * local_chord))
			if side < 0:
				ring.reverse()
			rings.append(ring)
		_loft(parent, rings, material)
		# Thin control-surface break, following the tapered trailing edge.
		var start := Vector3(side * span * 0.22, y + span * 0.44 * dihedral + chord * 0.025, z + sweep * 0.44 + lerpf(chord, tip_chord, 0.44) * 0.81)
		var end := Vector3(side * span * 0.47, y + span * 0.94 * dihedral + tip_chord * 0.025, z + sweep * 0.94 + lerpf(chord, tip_chord, 0.94) * 0.81)
		_rod(parent, start, end, 0.006, "seam")

static func _fin(parent: Node3D, position: Vector3, height: float, chord: float, sweep: float, material: String) -> void:
	var rings: Array = []
	for fraction in [0.0, 1.0]:
		var local_chord := chord * lerpf(1.0, 0.36, fraction)
		var z: float = position.z + sweep * fraction
		var t := 0.018 * lerpf(1.0, 0.35, fraction)
		var ring: Array[Vector3] = [Vector3(position.x, position.y + height * fraction, z),
			Vector3(position.x + t, position.y + height * fraction, z + local_chord * 0.3),
			Vector3(position.x, position.y + height * fraction, z + local_chord),
			Vector3(position.x - t, position.y + height * fraction, z + local_chord * 0.3)]
		ring.reverse()
		rings.append(ring)
	_loft(parent, rings, material)

static func _propeller(parent: Node3D, position: Vector3, radius: float, axis: Vector3, blades: int = 2) -> void:
	var pivot := Node3D.new()
	pivot.name = "Rotor_%d" % parent.get_child_count()
	pivot.position = position
	pivot.set_meta("axis", axis)
	parent.add_child(pivot)
	# Blade geometry lies perpendicular to the local Y axis, then is oriented once.
	for i in range(blades):
		var angle := i * TAU / blades
		var center := Vector3(cos(angle), 0, -sin(angle)) * radius * 0.48
		var blade := _ellipsoid(pivot, center, Vector3(radius * 1.04, 0.014, radius * 0.15), "carbon")
		blade.rotation.y = angle
		blade.rotation.x = 0.08
	if absf(axis.dot(Vector3.UP)) < 0.99:
		for child in pivot.get_children():
			child.transform = Transform3D(Basis(Vector3.RIGHT, PI * 0.5), Vector3.ZERO) * child.transform
	_rod(parent, position - axis * 0.045, position + axis * 0.055, radius * 0.105, "metal")
	_ellipsoid(parent, position + axis * 0.06, Vector3.ONE * radius * 0.22, "rubber")

static func _camera(parent: Node3D, position: Vector3, radius: float) -> void:
	_rod(parent, position + Vector3(0, radius * 1.5, 0), position, radius * 0.23, "metal")
	_ellipsoid(parent, position, Vector3.ONE * radius * 2.0, "paint")
	_rod(parent, position + Vector3(0, 0, -radius * 0.74), position + Vector3(0, 0, -radius * 1.07), radius * 0.62, "rubber")
	_ellipsoid(parent, position + Vector3(0, 0, -radius * 1.1), Vector3(radius, radius, radius * 0.11), "glass")

static func _fpv(parent: Node3D) -> void:
	# Open carbon sandwich frame with visible spacers and an exposed strapped pack.
	_box(parent, Vector3(0, -0.025, 0), Vector3(0.35, 0.035, 0.68), "carbon")
	_box(parent, Vector3(0, 0.12, 0.02), Vector3(0.32, 0.025, 0.6), "carbon")
	_box(parent, Vector3(0, 0.035, 0.015), Vector3(0.22, 0.045, 0.24), "green")
	_box(parent, Vector3(0, 0.25, 0.045), Vector3(0.3, 0.23, 0.49), "paint")
	_box(parent, Vector3(0, 0.369, 0.045), Vector3(0.19, 0.008, 0.19), "white")
	for z in [-0.12, 0.21]:
		_box(parent, Vector3(0, 0.375, z), Vector3(0.33, 0.024, 0.058), "rubber")
		for side in [-1.0, 1.0]:
			_box(parent, Vector3(side * 0.158, 0.255, z), Vector3(0.024, 0.24, 0.058), "rubber")
	for side in [-1.0, 1.0]:
		for z in [-0.27, 0.27]:
			_rod(parent, Vector3(side * 0.135, -0.005, z), Vector3(side * 0.135, 0.12, z), 0.02, "metal")
			_ellipsoid(parent, Vector3(side * 0.135, 0.14, z), Vector3(0.035, 0.012, 0.035), "metal")
	for i in range(4):
		var angle := PI / 4.0 + TAU * i / 4.0
		var endpoint := Vector3(cos(angle), 0, sin(angle)) * 0.82
		var arm := _box(parent, endpoint * 0.57 + Vector3(0, -0.025, 0), Vector3(0.105, 0.042, 0.72), "carbon")
		arm.rotation.y = atan2(endpoint.x, endpoint.z)
		_rod(parent, endpoint + Vector3(0, -0.065, 0), endpoint + Vector3(0, 0.04, 0), 0.083, "metal")
		_rod(parent, endpoint + Vector3(0, 0.015, 0), endpoint + Vector3(0, 0.09, 0), 0.089, "carbon")
		_propeller(parent, endpoint + Vector3(0, 0.11, 0), 0.35, Vector3.UP, 3)
		_ellipsoid(parent, endpoint + Vector3(0, -0.095, 0), Vector3(0.12, 0.085, 0.12), "rubber")
	var camera := Node3D.new()
	parent.add_child(camera)
	camera.position = Vector3(0, 0.065, -0.325)
	camera.rotation.x = 0.3
	_box(camera, Vector3.ZERO, Vector3(0.19, 0.17, 0.16), "metal")
	_rod(camera, Vector3(0, 0, -0.075), Vector3(0, 0, -0.15), 0.071, "rubber")
	_ellipsoid(camera, Vector3(0, 0, -0.154), Vector3(0.112, 0.112, 0.018), "glass")
	_flatten(camera, parent)
	_rod(parent, Vector3(0.04, 0.08, 0.3), Vector3(0.04, 0.47, 0.48), 0.018, "carbon")
	_ellipsoid(parent, Vector3(0.04, 0.49, 0.49), Vector3(0.105, 0.07, 0.105), "rubber")
	_rod(parent, Vector3(-0.11, 0.22, 0.3), Vector3(-0.12, 0.08, 0.4), 0.018, "red")
	_box(parent, Vector3(-0.12, 0.075, 0.405), Vector3(0.062, 0.05, 0.05), "olive")

static func _multirotor(parent: Node3D, hex: bool) -> void:
	_body(parent, Vector3.ZERO, 1.08, 0.65 if hex else 0.55, 0.28, "paint")
	_body(parent, Vector3(0, 0.09, 0.1), 0.62, 0.46, 0.18, "white")
	_box(parent, Vector3(0, 0.15, 0.08), Vector3(0.31, 0.05, 0.41), "carbon")
	for side in [-1.0, 1.0]:
		for index in range(4):
			_box(parent, Vector3(side * 0.245, 0.03, -0.08 + index * 0.065), Vector3(0.018, 0.065, 0.025), "rubber")
	var count := 6 if hex else 4
	for i in range(count):
		var angle := TAU * i / count + (0.0 if hex else PI / 4.0)
		var endpoint := Vector3(cos(angle), 0, sin(angle)) * (0.95 if hex else 0.8)
		var start := Vector3(endpoint.x * 0.21, -0.005, endpoint.z * 0.26)
		_rod(parent, start, endpoint + Vector3(0, 0.045, 0), 0.065, "carbon", 0.04)
		_rod(parent, endpoint + Vector3(0, -0.045, 0), endpoint + Vector3(0, 0.09, 0), 0.095, "metal")
		_rod(parent, endpoint + Vector3(0, 0.025, 0), endpoint + Vector3(0, 0.115, 0), 0.105, "rubber", 0.09)
		_propeller(parent, endpoint + Vector3(0, 0.13, 0), 0.39 if hex else 0.4, Vector3.UP)
		_ellipsoid(parent, endpoint + Vector3(0, -0.06, 0), Vector3(0.075, 0.04, 0.07), "red" if endpoint.z < 0 else "green")
	for side in [-1.0, 1.0]:
		for z in [-0.3, 0.32]:
			_rod(parent, Vector3(side * 0.2, -0.07, z), Vector3(side * 0.36, -0.4, z), 0.026, "carbon")
		_rod(parent, Vector3(side * 0.36, -0.4, -0.41), Vector3(side * 0.36, -0.4, 0.45), 0.032, "rubber")
	_camera(parent, Vector3(0, -0.25, -0.35), 0.115)

static func _fixed_wing(parent: Node3D, id: String) -> void:
	match id:
		"geran_2", "garpiya", "geran_3", "gerbera":
			var small := id == "gerbera"
			var span := 3.0 if id == "garpiya" else (2.55 if small else 2.7)
			var length := 2.7 if id == "garpiya" else (2.2 if small else 2.5)
			_body(parent, Vector3.ZERO, length, 0.36 if small else 0.42, 0.36, "olive" if id == "garpiya" else "paint")
			_wing(parent, span, 1.78 if not small else 1.5, 0.35, 1.45, -0.82, -0.05, "paint", 0.0)
			if small:
				_fin(parent, Vector3(0, 0.09, 0.65), 0.52, 0.52, 0.1, "white")
			else:
				for side in [-1.0, 1.0]:
					_fin(parent, Vector3(side * span * 0.495, -0.02, 0.64), 0.4, 0.37, 0.08, "paint")
			if id == "geran_3":
				_body(parent, Vector3(0, 0.18, 0.42), 1.02, 0.27, 0.32, "metal")
				_rod(parent, Vector3(0, 0.21, 0.96), Vector3(0, 0.21, 1.2), 0.115, "rubber")
				_ellipsoid(parent, Vector3(0, 0.23, -0.03), Vector3(0.22, 0.21, 0.035), "rubber")
			else:
				_rod(parent, Vector3(0, 0, length * 0.44), Vector3(0, 0, length * 0.55), 0.13, "metal")
				_propeller(parent, Vector3(0, 0, length * 0.56), 0.39, Vector3.BACK)
		"lancet":
			_body(parent, Vector3.ZERO, 2.7, 0.25, 0.25, "white")
			for z in [-0.68, 0.58]:
				for angle in [-PI / 4.0, PI / 4.0]:
					var wing_root := Node3D.new()
					parent.add_child(wing_root)
					_wing(wing_root, 1.5 if z < 0 else 1.25, 0.3, 0.18, 0.1, z, 0, "white", 0)
					wing_root.rotation.z = angle
					_flatten(wing_root, parent)
			_ellipsoid(parent, Vector3(0, 0, -1.29), Vector3(0.19, 0.19, 0.12), "glass")
			_propeller(parent, Vector3(0, 0, 1.4), 0.29, Vector3.BACK)
		"zala", "supercam":
			var broad := id == "supercam"
			_body(parent, Vector3(0, 0.02, 0), 1.15, 0.4, 0.23, "white")
			_wing(parent, 3.2 if broad else 2.6, 0.9 if broad else 0.74, 0.21, 0.59 if broad else 0.38, -0.37, 0, "white")
			for side in [-1.0, 1.0]:
				_fin(parent, Vector3(side * (1.58 if broad else 1.28), 0.08, 0.26 if broad else 0.06), 0.26 if broad else 0.16, 0.22, 0.06, "carbon")
			_camera(parent, Vector3(0, -0.15, -0.2), 0.08)
			_propeller(parent, Vector3(0, 0, 0.64), 0.27, Vector3.BACK)
		_:
			_conventional(parent, id)

static func _conventional(parent: Node3D, id: String) -> void:
	var large := id == "orlan_30"
	var simple := id in ["parodiya", "molniya"]
	var length := 2.35 if large else 2.1
	_body(parent, Vector3.ZERO, length, 0.32 if large else 0.27, 0.33 if large else 0.27, "olive" if simple else "white")
	_wing(parent, 3.5 if large else 3.1, 0.53 if simple else 0.64, 0.31, 0.12, -0.34, 0.16, "paint" if simple else "white")
	if id == "molniya":
		for side in [-1.0, 1.0]:
			_rod(parent, Vector3(side * 0.61, 0.1, 0.1), Vector3(side * 0.61, 0.1, 1.43), 0.035, "carbon")
			_fin(parent, Vector3(side * 0.61, 0.1, 1.07), 0.43, 0.37, 0.13, "paint")
		_wing(parent, 1.32, 0.36, 0.32, 0, 1.07, 0.12, "paint", 0)
		_propeller(parent, Vector3(0, 0, 1.14), 0.36, Vector3.BACK)
	else:
		_wing(parent, 1.12 if large else 0.98, 0.36, 0.2, 0.13, length * 0.35, 0.07, "paint", 0)
		_fin(parent, Vector3(0, 0.07, length * 0.3), 0.47, 0.48, 0.23, "paint")
		_propeller(parent, Vector3(0, 0, -length * 0.51), 0.36 if large else 0.3, Vector3.FORWARD)
	if not simple:
		_camera(parent, Vector3(0, -0.24 if large else -0.16, -0.23), 0.16 if large else 0.09)
		_rod(parent, Vector3(0, 0.13, 0.24), Vector3(0, 0.48, 0.35), 0.009, "carbon")
		_ellipsoid(parent, Vector3(0, 0.16, -0.5), Vector3(0.2, 0.035, 0.31), "seam")

static func _flatten(group: Node3D, parent: Node3D) -> void:
	for child in group.get_children():
		var transformed: Transform3D = group.transform * child.transform
		group.remove_child(child)
		parent.add_child(child)
		child.transform = transformed
	group.free()

## One static mesh per model, one surface per finish. Rotor pivots remain animatable.
static func _merge_static(parent: Node3D) -> void:
	var surfaces: Dictionary = {}
	for child in parent.get_children():
		if child is not MeshInstance3D:
			continue
		var material: Material = child.material_override
		if not surfaces.has(material):
			var surface := SurfaceTool.new()
			surface.begin(Mesh.PRIMITIVE_TRIANGLES)
			surfaces[material] = surface
		for i in range(child.mesh.get_surface_count()):
			surfaces[material].append_from(child.mesh, i, child.transform)
		child.free()
	var merged := ArrayMesh.new()
	for material in surfaces:
		surfaces[material].set_material(material)
		surfaces[material].commit(merged)
	var part := MeshInstance3D.new()
	part.name = "Airframe"
	part.mesh = merged
	parent.add_child(part)
