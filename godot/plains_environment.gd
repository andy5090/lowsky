extends RefCounted

const Geographic = preload("res://geographic_environment.gd")
## Art-direction test: fictional plains, fields and shelterbelts. No map data.

static func elevation(x: float, z: float, noise: FastNoiseLite, layout: Dictionary) -> float:
	# Share the fence dimensions and grading margin with the map and DEM.
	var outside_site = Geographic.grading_distance(x, z, layout)
	return noise.get_noise_2d(x, z) * 18.0 * smoothstep(0, float(layout.terrain_grading.blend_m), outside_site) - 0.02

static func patch(rect: Rect2, material: Material, noise: FastNoiseLite, layout: Dictionary, lift: float = 0.0) -> MeshInstance3D:
	var surface = SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	# A 100 m grid bounds the 10 km landscape at 20,000 triangles.
	var columns = maxi(1, ceili(rect.size.x / 100.0))
	var rows = maxi(1, ceili(rect.size.y / 100.0))
	for z in range(rows):
		for x in range(columns):
			var points: Array[Vector3] = []
			for offset in [Vector2(0, 0), Vector2(1, 0), Vector2(0, 1), Vector2(1, 1)]:
				var px = rect.position.x + (x + offset.x) * rect.size.x / columns
				var pz = rect.position.y + (z + offset.y) * rect.size.y / rows
				points.append(Vector3(px, elevation(px, pz, noise, layout) + lift, pz))
			for index in [0, 1, 2, 1, 3, 2]:
				surface.add_vertex(points[index])
	surface.index()
	surface.generate_normals()
	var node = MeshInstance3D.new()
	node.mesh = surface.commit()
	node.material_override = material
	return node

static func make(grass: StandardMaterial3D, layout: Dictionary) -> Node3D:
	var root = Node3D.new()
	root.name = "PlainsTerrain"
	var noise = FastNoiseLite.new()
	noise.seed = 6149
	noise.frequency = 0.0005
	root.set_meta("width_m", 10000)
	root.set_meta("length_m", 10000)
	root.add_child(patch(Rect2(-5000, -5000, 10000, 10000), grass, noise, layout))
	var fields = Node3D.new()
	fields.name = "Fields"
	root.add_child(fields)
	var palette = [Color("a18a55"), Color("6d794d"), Color("807951"), Color("596247"), Color("938566")]
	var field_materials: Array[StandardMaterial3D] = []
	for color in palette:
		var material = grass.duplicate() as StandardMaterial3D
		material.albedo_color = color
		material.normal_scale = 0.08
		field_materials.append(material)
	# Farm parcels are outside the whole enclosure, not between its facilities.
	var half_site = Vector2(float(layout.perimeter.width_m), float(layout.perimeter.length_m)) * 0.5 + Vector2.ONE * float(layout.terrain_grading.margin_m)
	var clear_site = Rect2(-half_site, half_site * 2.0)
	for z in range(-7, 7):
		for x in range(-7, 7):
			var rect = Rect2(x * 650 + 15, z * 650 + 15, 620, 620)
			if rect.intersects(clear_site):
				continue
			var material = field_materials[posmod(x * 3 + z * 7, palette.size())]
			fields.add_child(patch(rect, material, noise, layout, 0.12))
	var road_material = grass.duplicate() as StandardMaterial3D
	road_material.albedo_color = Color("89857a")
	road_material.normal_enabled = false
	var road = patch(Rect2(-4000, -half_site.y - 250, 8000, 6), road_material, noise, layout, 0.16)
	road.name = "FarmLane"
	root.add_child(road)
	add_shelterbelts(root, noise, layout)
	return root

static func add_shelterbelts(root: Node3D, noise: FastNoiseLite, layout: Dictionary) -> void:
	var rng = RandomNumberGenerator.new()
	rng.seed = 9317
	var trees: Array[Vector3] = []
	for side in [-1, 1]:
		for index in range(90):
			var x = side * (float(layout.perimeter.width_m) * 0.5 + 250) + rng.randf_range(-4, 4)
			var z = (index / 89.0 - 0.5) * (float(layout.perimeter.length_m) + 500)
			trees.append(Vector3(x, elevation(x, z, noise, layout), z))
		for index in range(70):
			var x = (index / 69.0 - 0.5) * (float(layout.perimeter.width_m) + 100)
			var z = side * (float(layout.perimeter.length_m) * 0.5 + 250) + rng.randf_range(-4, 4)
			trees.append(Vector3(x, elevation(x, z, noise, layout), z))
	var belt = Node3D.new()
	belt.name = "Shelterbelts"
	root.add_child(belt)
	# Instanced procedural foliage is intended for the middle distance.
	for layer in range(4):
		var mesh: Mesh
		var material = StandardMaterial3D.new()
		material.roughness = 1.0
		material.metallic_specular = 0.0
		if layer == 0:
			var trunk = CylinderMesh.new()
			trunk.top_radius = 0.10
			trunk.bottom_radius = 0.18
			trunk.height = 4
			trunk.radial_segments = 5
			mesh = trunk
			material.albedo_color = Color("403c2c")
		else:
			mesh = foliage_mesh(rng)
			material.albedo_color = [Color("263825"), Color("354a2c"), Color("445531")][layer - 1]
			material.vertex_color_use_as_albedo = true
			material.cull_mode = BaseMaterial3D.CULL_DISABLED
		var instances = MultiMesh.new()
		instances.transform_format = MultiMesh.TRANSFORM_3D
		instances.mesh = mesh
		instances.instance_count = trees.size()
		for index in range(trees.size()):
			var scale = rng.randf_range(0.8, 1.25)
			var position = trees[index] + Vector3(0, 2 * scale, 0)
			if layer > 0:
				position += Vector3(rng.randf_range(-1, 1), 2.2 + (layer - 1) * 0.6, rng.randf_range(-1, 1))
			instances.set_instance_transform(index, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * scale), position))
		var node = MultiMeshInstance3D.new()
		node.multimesh = instances
		node.material_override = material
		belt.add_child(node)

static func foliage_mesh(rng: RandomNumberGenerator) -> ArrayMesh:
	var surface = SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for leaf in range(650):
		var direction = Vector3(rng.randf_range(-1, 1), rng.randf_range(-1, 1), rng.randf_range(-1, 1)).normalized()
		var center = direction * pow(rng.randf(), 0.333) * Vector3(1.8, 2.4, 1.7)
		var normal = Vector3(rng.randf_range(-1, 1), rng.randf_range(0.1, 1), rng.randf_range(-1, 1)).normalized()
		var horizontal = normal.cross(Vector3.FORWARD).normalized() * rng.randf_range(0.18, 0.35)
		var vertical = normal.cross(horizontal).normalized() * rng.randf_range(0.25, 0.48)
		var color = Color.WHITE * rng.randf_range(0.65, 1.0)
		color.a = 1
		surface.set_color(color)
		surface.set_normal(normal)
		for offset in [-horizontal, vertical, horizontal, -horizontal, horizontal, -vertical]:
			surface.add_vertex(center + offset)
	return surface.commit()
