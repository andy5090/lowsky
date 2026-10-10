extends RefCounted
## Visual geometry for a fictional base; dimensions are scene units, not a survey.

static func box(root: Node3D, size: Vector3, position: Vector3, material: Material) -> MeshInstance3D:
	var node = MeshInstance3D.new()
	var mesh = BoxMesh.new()
	mesh.size = size
	node.mesh = mesh
	node.material_override = material
	node.position = position
	root.add_child(node)
	return node

static func rod(root: Node3D, start: Vector3, end: Vector3, radius: float, material: Material) -> MeshInstance3D:
	var node = MeshInstance3D.new()
	var mesh = CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = start.distance_to(end)
	mesh.radial_segments = 8
	node.mesh = mesh
	node.material_override = material
	node.position = (start + end) * 0.5
	var direction = (end - start).normalized()
	node.quaternion = Quaternion(Vector3.UP, direction)
	root.add_child(node)
	return node

static func make_hangar(m: Dictionary) -> Node3D:
	var root = Node3D.new()
	root.name = "DetailedHangar"
	box(root, Vector3(12, 0.25, 15), Vector3(0, 0.1, 0.8), m.concrete)
	for side in [-1, 1]:
		box(root, Vector3(0.18, 4.6, 12), Vector3(side * 5, 2.55, 0), m.metal)
		box(root, Vector3(0.28, 0.65, 12), Vector3(side * 5, 0.5, 0), m.concrete)
		var roof = box(root, Vector3(5.45, 0.16, 12.7), Vector3(side * 2.6, 5.4, 0), m.metal)
		roof.rotation.z = side * deg_to_rad(-12)
		rod(root, Vector3(side * 5.28, 4.9, -6.2), Vector3(side * 5.28, 4.9, 6.2), 0.09, m.dark_metal)
		rod(root, Vector3(side * 5.3, 0.3, -5.8), Vector3(side * 5.3, 4.9, -5.8), 0.07, m.dark_metal)
		# Partially open sliding doors, independently replaceable display geometry.
		box(root, Vector3(2.45, 4.3, 0.15), Vector3(side * 4.12, 2.4, 6.15), m.painted_metal)
		for panel in range(6):
			box(root, Vector3(0.035, 4.25, 0.055), Vector3(side * 4.12 - 1.05 + panel * 0.42, 2.4, 6.25), m.dark_metal)
		for z in [-5.5, -2.0, 1.5, 5.5]:
			box(root, Vector3(0.2, 4.8, 0.2), Vector3(side * 4.75, 2.6, z), m.dark_metal)
			rod(root, Vector3(side * 4.75, 4.8, z), Vector3(0, 5.98, z), 0.09, m.dark_metal)
	box(root, Vector3(10, 4.6, 0.18), Vector3(0, 2.55, -6), m.metal)
	box(root, Vector3(10.8, 0.2, 0.24), Vector3(0, 4.9, 6.25), m.dark_metal)
	box(root, Vector3(0.15, 0.15, 12.8), Vector3(0, 5.98, 0), m.dark_metal)
	for z in [-5.5, -2.0, 1.5, 5.5]:
		rod(root, Vector3(-4.75, 4.75, z), Vector3(4.75, 4.75, z), 0.07, m.dark_metal)
		rod(root, Vector3(0, 4.75, z), Vector3(0, 5.9, z), 0.07, m.dark_metal)
	for side in [-1, 1]:
		for index in range(6):
			box(root, Vector3(0.07, 0.7, 1.15), Vector3(side * 5.12, 3.8, -4.6 + index * 1.8), m.glass)
	return root

static func make_tower(m: Dictionary) -> Node3D:
	var root = Node3D.new()
	root.name = "DetailedTower"
	box(root, Vector3(6, 0.4, 6), Vector3(0, 0.2, 0), m.concrete)
	box(root, Vector3(3.2, 7.8, 3.2), Vector3(0, 4.3, 0), m.concrete)
	box(root, Vector3(1, 2.2, 0.12), Vector3(0, 1.5, 1.66), m.dark_metal)
	for y in [3.5, 5.5, 7.5]:
		box(root, Vector3(0.65, 1, 0.06), Vector3(0, y, 1.66), m.glass)
	for index in range(3):
		box(root, Vector3(1.8, 0.14, 0.4), Vector3(0, 0.08 + index * 0.14, 2.6 - index * 0.4), m.concrete)
	box(root, Vector3(5.8, 0.3, 5.8), Vector3(0, 8.35, 0), m.painted_metal)
	box(root, Vector3(4.5, 0.65, 4.5), Vector3(0, 8.8, 0), m.painted_metal)
	box(root, Vector3(4.5, 1.45, 4.5), Vector3(0, 9.8, 0), m.glass)
	box(root, Vector3(5.25, 0.22, 5.25), Vector3(0, 10.65, 0), m.dark_metal)
	for side in [-1, 1]:
		for offset in [-2.25, -0.75, 0.75, 2.25]:
			box(root, Vector3(0.075, 1.6, 0.075), Vector3(offset, 9.8, side * 2.29), m.dark_metal)
			box(root, Vector3(0.075, 1.6, 0.075), Vector3(side * 2.29, 9.8, offset), m.dark_metal)
		for height in [8.8, 9.2]:
			rod(root, Vector3(-2.8, height, side * 2.8), Vector3(2.8, height, side * 2.8), 0.035, m.dark_metal)
			rod(root, Vector3(side * 2.8, height, -2.8), Vector3(side * 2.8, height, 2.8), 0.035, m.dark_metal)
		for offset in [-2.8, 0, 2.8]:
			rod(root, Vector3(offset, 8.5, side * 2.8), Vector3(offset, 9.2, side * 2.8), 0.035, m.dark_metal)
			rod(root, Vector3(side * 2.8, 8.5, offset), Vector3(side * 2.8, 9.2, offset), 0.035, m.dark_metal)
	rod(root, Vector3(0, 10.8, 0), Vector3(0, 13, 0), 0.045, m.dark_metal)
	return root

static func make_utility_building(m: Dictionary) -> Node3D:
	var root = Node3D.new()
	root.name = "DetailedUtilityBuilding"
	box(root, Vector3(6.4, 0.3, 8.4), Vector3(0, 0.15, 0), m.concrete)
	box(root, Vector3(6, 3.3, 8), Vector3(0, 1.9, 0), m.concrete)
	box(root, Vector3(6.5, 0.2, 8.5), Vector3(0, 3.65, 0), m.metal)
	for x in [-1.8, 0, 1.8]:
		box(root, Vector3(1.3, 1.15, 0.07), Vector3(x, 2.2, 4.07), m.glass)
		box(root, Vector3(1.45, 0.08, 0.16), Vector3(x, 1.6, 4.07), m.dark_metal)
	box(root, Vector3(0.07, 2.2, 1.1), Vector3(-3.08, 1.45, 2.4), m.dark_metal)
	for z in [-2, 1]:
		box(root, Vector3(1.5, 0.65, 1.2), Vector3(0, 4, z), m.painted_metal)
		for index in range(6):
			box(root, Vector3(1.25, 0.035, 0.04), Vector3(0, 3.8 + index * 0.08, z + 0.63), m.dark_metal)
	return root

static func make_terrain(material: Material, layout: Dictionary) -> Node3D:
	var root = Node3D.new()
	root.name = "FictionalTerrain"
	# Low distant terrain, deliberately fictional and outside the replay area.
	var noise = FastNoiseLite.new()
	noise.seed = 6149
	noise.frequency = 0.0008
	var surface = SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	root.set_meta("width_m", 10000)
	root.set_meta("length_m", 10000)
	for z in range(-50, 50):
		for x in range(-50, 50):
			var points: Array[Vector3] = []
			for offset in [Vector2(0, 0), Vector2(1, 0), Vector2(0, 1), Vector2(1, 1)]:
				var px = (x + offset.x) * 100
				var pz = (z + offset.y) * 100
				var outside_site = maxf(absf(px) - float(layout.perimeter.width_m) * 0.5 - float(layout.terrain_grading.margin_m), absf(pz) - float(layout.perimeter.length_m) * 0.5 - float(layout.terrain_grading.margin_m))
				var blend = smoothstep(0, float(layout.terrain_grading.blend_m), outside_site)
				var height = maxf(0, noise.get_noise_2d(px, pz) + 0.35) * 220 * blend - 0.02
				points.append(Vector3(px, height, pz))
			for index in [0, 1, 2, 1, 3, 2]:
				surface.add_vertex(points[index])
	surface.index()
	surface.generate_normals()
	var hills = MeshInstance3D.new()
	hills.mesh = surface.commit()
	hills.material_override = material
	root.add_child(hills)
	return root
