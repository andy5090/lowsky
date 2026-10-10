extends RefCounted
## DEM-backed terrain: local X points east, Z south, and Y is relative elevation.
## Only the fictional site's level surface and its blend are modified.

static func elevation(data: Dictionary, x: float, z: float, layout: Dictionary) -> float:
	var outside_site = maxf(absf(x) - (float(layout.perimeter.width_m) * 0.5 + float(layout.terrain_grading.margin_m)), absf(z) - (float(layout.perimeter.length_m) * 0.5 + float(layout.terrain_grading.margin_m)))
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

static func make(data: Dictionary, grass: StandardMaterial3D, layout: Dictionary) -> Node3D:
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
	root.set_meta("flat_site_half_extents_m", Vector2((float(layout.perimeter.width_m) * 0.5 + float(layout.terrain_grading.margin_m)), (float(layout.perimeter.length_m) * 0.5 + float(layout.terrain_grading.margin_m))))
	root.set_meta("site_blend_width_m", float(layout.terrain_grading.blend_m))
	root.set_meta("triangle_count", 2 * (grid_size - 1) * (grid_size - 1))
	var surface = SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for row in range(grid_size):
		var z = row * spacing - extent * 0.5
		for column in range(grid_size):
			var x = column * spacing - extent * 0.5
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
	root.add_child(mesh)
	return root
