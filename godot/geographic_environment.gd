extends RefCounted
## DEM-backed terrain: local X points east, Z south, and Y is relative elevation.
## Only the fictional site's level surface and its blend are modified.

static func grading_distance(x: float, z: float, layout: Dictionary) -> float:
	var point = Vector2(x, z)
	var polygon = PackedVector2Array()
	for corner in layout.perimeter.polygon:
		polygon.append(Vector2(corner[0], corner[1]))
	if Geometry2D.is_point_in_polygon(point, polygon):
		return -float(layout.terrain_grading.margin_m)
	var distance = INF
	for index in range(polygon.size()):
		var nearest = Geometry2D.get_closest_point_to_segment(point, polygon[index], polygon[(index + 1) % polygon.size()])
		distance = minf(distance, point.distance_to(nearest))
	return distance - float(layout.terrain_grading.margin_m)

static func elevation(data: Dictionary, x: float, z: float, layout: Dictionary) -> float:
	var outside_site = grading_distance(x, z, layout)
	if outside_site <= 0.0:
		return -0.02
	var grid_size = int(data.grid_size)
	var half_extent = float(data.extent_m) * 0.5
	var spacing = float(data.spacing_m)
	# Rows run north to south, matching increasing local Z.
	var column = clampf((x + half_extent) / spacing, 0.0, grid_size - 1.0)
	var row = clampf((z + half_extent) / spacing, 0.0, grid_size - 1.0)
	var x0 = floori(column)
	var z0 = floori(row)
	var x1 = mini(x0 + 1, grid_size - 1)
	var z1 = mini(z0 + 1, grid_size - 1)
	var heights: Array = data.heights_m
	var north = lerpf(float(heights[z0][x0]), float(heights[z0][x1]), column - x0)
	var south = lerpf(float(heights[z1][x0]), float(heights[z1][x1]), column - x0)
	var relative_height = lerpf(north, south, row - z0) - float(data.reference_elevation_m)
	return lerpf(-0.02, relative_height, smoothstep(0.0, float(layout.terrain_grading.blend_m), outside_site))

static func surface_height(vertices: PackedVector3Array, grid_size: int, spacing: float, x: float, z: float) -> float:
	# Interpolate the actual triangle, including grading, rather than the bilinear DEM.
	var half = (grid_size - 1) * spacing * 0.5
	var column = clampf((x + half) / spacing, 0, grid_size - 1)
	var row = clampf((z + half) / spacing, 0, grid_size - 1)
	var ix = mini(floori(column), grid_size - 2)
	var iz = mini(floori(row), grid_size - 2)
	var u = column - ix
	var v = row - iz
	var corner = iz * grid_size + ix
	if u + v <= 1.0:
		return vertices[corner].y * (1.0 - u - v) + vertices[corner + 1].y * u + vertices[corner + grid_size].y * v
	return vertices[corner + 1].y * (1.0 - v) + vertices[corner + grid_size].y * (1.0 - u) + vertices[corner + grid_size + 1].y * (u + v - 1.0)

static func make(data: Dictionary, grass: StandardMaterial3D, layout: Dictionary, context: Dictionary = {}) -> Node3D:
	var grid_size = int(data.grid_size)
	var spacing = float(data.spacing_m)
	var extent = float(data.extent_m)
	assert(grid_size >= 2 and grid_size <= 201, "Terrain grid must have 2–201 samples per side")
	assert(spacing > 0.0 and is_equal_approx(extent, spacing * (grid_size - 1)), "Terrain extent must match grid spacing")
	assert(data.heights_m.size() == grid_size, "Terrain row count must match grid_size")
	for row in data.heights_m:
		assert(row.size() == grid_size, "Terrain column count must match grid_size")
	var root = Node3D.new()
	root.name = "GeographicTerrain"
	root.set_meta("unit", "meter")
	root.set_meta("origin", data.origin)
	root.set_meta("source", data.get("source", "Supplied elevation grid"))
	root.set_meta("reference_elevation_m", data.reference_elevation_m)
	root.set_meta("width_m", extent)
	root.set_meta("length_m", extent)
	root.set_meta("site_modified", true)
	root.set_meta("flat_site_polygon", layout.perimeter.polygon)
	root.set_meta("flat_site_margin_m", layout.terrain_grading.margin_m)
	root.set_meta("site_blend_width_m", float(layout.terrain_grading.blend_m))
	root.set_meta("triangle_count", 2 * (grid_size - 1) * (grid_size - 1))
	var surface = SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for row in range(grid_size):
		var z = row * spacing - extent * 0.5
		for column in range(grid_size):
			var x = column * spacing - extent * 0.5
			var site_mask = 1.0 - smoothstep(0.0, 100.0, grading_distance(x, z, layout))
			surface.set_color(Color(site_mask, 0, 0, 1))
			surface.set_uv(Vector2(x, z))
			surface.add_vertex(Vector3(x, elevation(data, x, z, layout), z))
	for row in range(grid_size - 1):
		for column in range(grid_size - 1):
			var corner = row * grid_size + column
			for index in [corner, corner + 1, corner + grid_size, corner + 1, corner + grid_size + 1, corner + grid_size]:
				surface.add_index(index)
	surface.generate_normals()
	var mesh = MeshInstance3D.new()
	mesh.name = "ElevationSurface"
	mesh.mesh = surface.commit()
	mesh.material_override = grass
	if not context.is_empty():
		var mapped = ShaderMaterial.new()
		mapped.shader = load("res://geographic_ground.gdshader")
		mapped.set_shader_parameter("satellite", load("res://assets/terrain/korea_satellite.png"))
		mapped.set_shader_parameter("grass_detail", grass.albedo_texture)
		mapped.set_shader_parameter("extent_m", extent)
		mesh.material_override = mapped
	root.add_child(mesh)
	if not context.is_empty():
		assert(context.origin == data.origin and float(context.extent_m) == extent, "Terrain context must share the DEM origin and extent")
		var cover = (load("res://assets/terrain/korea_landcover.png") as Texture2D).get_image()
		var vertices: PackedVector3Array = mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var height_at = func(x: float, z: float) -> float: return surface_height(vertices, grid_size, spacing, x, z)
		root.add_child(load("res://geographic_context.gd").make(context, cover, height_at, layout))
	return root
