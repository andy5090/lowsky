extends RefCounted
## Public-map surroundings. X east, Z south; all placement is in local meters.
## Tree locations are illustrative samples inside mapped tree-cover pixels.

const TREE_LIMIT = 60000
const TREE_SPACING = 14.0
const BIN_SIZE = 100.0
const CHUNK_SIZE = 500.0

static func make(context: Dictionary, landcover: Image, height_at: Callable, layout: Dictionary) -> Node3D:
	var root = Node3D.new()
	root.name = "GeographicContext"
	var extent = float(context.get("extent_m", 10000.0))
	var site = _polygon(layout.get("perimeter", {}).get("polygon", []))
	var margins = Geometry2D.offset_polygon(site, float(layout.get("terrain_grading", {}).get("margin_m", 0.0))) if site.size() >= 3 else []
	var exclusion: PackedVector2Array = margins[0] if not margins.is_empty() else site
	var bins: Dictionary = {}
	var roads = Node3D.new()
	roads.name = "Roads"
	root.add_child(roads)
	root.set_meta("road_count", _roads(roads, context.get("roads", []), height_at, extent, exclusion, bins))
	var buildings = Node3D.new()
	buildings.name = "Buildings"
	root.add_child(buildings)
	root.set_meta("building_count", _buildings(buildings, context.get("buildings", []), height_at, extent, exclusion, bins))
	var forest = Node3D.new()
	forest.name = "Forest"
	root.add_child(forest)
	root.set_meta("tree_count", _forest(forest, landcover, height_at, extent, exclusion, bins))
	root.set_meta("origin", context.get("origin", {}))
	root.set_meta("extent_m", extent)
	root.set_meta("tree_placement", "Deterministic samples inside ESA tree-cover pixels; not surveyed individual trees")
	return root

static func _polygon(points: Array, closed: bool = true) -> PackedVector2Array:
	var polygon = PackedVector2Array()
	for point in points:
		var vertex = Vector2(float(point[0]), float(point[1]))
		if polygon.is_empty() or not vertex.is_equal_approx(polygon[-1]):
			polygon.append(vertex)
	if closed and polygon.size() > 2 and polygon[0].is_equal_approx(polygon[-1]):
		polygon.remove_at(polygon.size() - 1)
	return polygon

static func _surface() -> SurfaceTool:
	var surface = SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	return surface

static func _material(color: Color, vertex_colors: bool = false) -> StandardMaterial3D:
	var material = StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.96
	material.metallic_specular = 0.08
	material.vertex_color_use_as_albedo = vertex_colors
	# Imported polygons may have either winding; normals are set per face.
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material

static func _triangle(surface: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, color: Color = Color.WHITE) -> void:
	# Godot uses clockwise front faces, including for two-sided lighting.
	var normal = (c - a).cross(b - a).normalized()
	surface.set_normal(normal)
	surface.set_color(color)
	for point in [a, b, c]:
		surface.add_vertex(point)

static func _finish(parent: Node3D, surface: SurfaceTool, material: Material, node_name: String) -> void:
	var arrays = surface.commit_to_arrays()
	if arrays[Mesh.ARRAY_VERTEX] == null or arrays[Mesh.ARRAY_VERTEX].is_empty():
		return
	var mesh = ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var instance = MeshInstance3D.new()
	instance.name = node_name
	instance.mesh = mesh
	instance.material_override = material
	parent.add_child(instance)

static func _inside(point: Vector2, site: PackedVector2Array) -> bool:
	return site.size() >= 3 and Geometry2D.is_point_in_polygon(point, site)

static func _ground(point: Vector2, height_at: Callable, lift: float = 0.0) -> Vector3:
	return Vector3(point.x, float(height_at.call(point.x, point.y)) + lift, point.y)

static func _index(bins: Dictionary, bounds: Rect2, object: Dictionary) -> void:
	for z in range(floori(bounds.position.y / BIN_SIZE), floori(bounds.end.y / BIN_SIZE) + 1):
		for x in range(floori(bounds.position.x / BIN_SIZE), floori(bounds.end.x / BIN_SIZE) + 1):
			var key = Vector2i(x, z)
			if not bins.has(key):
				bins[key] = []
			bins[key].append(object)

static func _blocked(point: Vector2, bins: Dictionary) -> bool:
	var key = Vector2i(floori(point.x / BIN_SIZE), floori(point.y / BIN_SIZE))
	for object in bins.get(key, []):
		if object.has("polygon"):
			if _inside(point, object.polygon):
				return true
		else:
			var nearest = Geometry2D.get_closest_point_to_segment(point, object.a, object.b)
			if point.distance_squared_to(nearest) < float(object.radius) * float(object.radius):
				return true
	return false

static func _roads(parent: Node3D, data: Array, height_at: Callable, extent: float, site: PackedVector2Array, bins: Dictionary) -> int:
	var surfaces = [_surface(), _surface(), _surface()]
	var count = 0
	var half = extent * 0.5
	for road in data:
		var points = _polygon(road.get("points", []), false)
		var kind = str(road.get("kind", "residential"))
		var major = kind in ["motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link", "primary_link"]
		var unpaved = kind in ["track", "path", "footway", "cycleway", "steps"]
		var width = clampf(float(road.get("width_m", 10.0 if major else 4.0)), 1.0, 36.0)
		var surface: SurfaceTool = surfaces[2 if unpaved else (0 if major else 1)]
		var drawn = false
		for index in range(points.size() - 1):
			var a = points[index]
			var b = points[index + 1]
			var length = a.distance_to(b)
			if length < 0.05:
				continue
			var side = Vector2(-(b - a).y, (b - a).x).normalized() * width * 0.5
			var steps = maxi(1, ceili(length / 16.0))
			for step in range(steps):
				var start = a.lerp(b, float(step) / steps)
				var end = a.lerp(b, float(step + 1) / steps)
				var corners = [start - side, start + side, end - side, end + side]
				var valid = true
				for corner in corners:
					if absf(corner.x) > half or absf(corner.y) > half or _inside(corner, site):
						valid = false
				if not valid or _inside((start + end) * 0.5, site):
					continue
				var verts: Array[Vector3] = []
				for corner in corners:
					verts.append(_ground(corner, height_at, 0.32))
				_triangle(surface, verts[0], verts[1], verts[2])
				_triangle(surface, verts[1], verts[3], verts[2])
				var bounds = Rect2(start, Vector2.ZERO).expand(end).grow(width * 0.5 + 7.0)
				_index(bins, bounds, {"a": start, "b": end, "radius": width * 0.5 + 7.0})
				drawn = true
		if drawn:
			count += 1
	for index in range(surfaces.size()):
		_finish(parent, surfaces[index], _material([Color("555757"), Color("70706b"), Color("9a917c")][index]), ["MainRoads", "LocalRoads", "RuralPaths"][index])
	return count

static func _bounds(polygon: PackedVector2Array) -> Rect2:
	var bounds = Rect2(polygon[0], Vector2.ZERO)
	for point in polygon:
		bounds = bounds.expand(point)
	return bounds

static func _buildings(parent: Node3D, data: Array, height_at: Callable, extent: float, site: PackedVector2Array, bins: Dictionary) -> int:
	var walls = _surface()
	var roofs = _surface()
	var count = 0
	var rng = RandomNumberGenerator.new()
	rng.seed = 53117
	var half = extent * 0.5
	var limits = PackedVector2Array([Vector2(-half, -half), Vector2(half, -half), Vector2(half, half), Vector2(-half, half)])
	for building in data:
		var polygon = _polygon(building.get("polygon", []))
		if polygon.size() < 3:
			continue
		# The fictional redevelopment replaces complete overlapping footprints.
		if site.size() >= 3 and not Geometry2D.intersect_polygons(polygon, site).is_empty():
			continue
		var clipped = Geometry2D.intersect_polygons(polygon, limits)
		if clipped.is_empty():
			continue
		var drawn = false
		for footprint in clipped:
			var indices = Geometry2D.triangulate_polygon(footprint)
			if indices.is_empty():
				continue
			var height = clampf(float(building.get("height_m", 7.0)), 2.5, 180.0)
			var foundation = -INF
			for point in footprint:
				foundation = maxf(foundation, float(height_at.call(point.x, point.y)))
			var eaves = foundation + height
			var wall_color: Color = [Color("c2bbb0"), Color("aaaeb0"), Color("d2cfbd"), Color("a39b91")][rng.randi_range(0, 3)]
			var roof_color: Color = [Color("667c88"), Color("777a77"), Color("a58170"), Color("54788d"), Color("b6b4a6")][rng.randi_range(0, 4)]
			for index in range(footprint.size()):
				var a: Vector2 = footprint[index]
				var b: Vector2 = footprint[(index + 1) % footprint.size()]
				var bottom_a = _ground(a, height_at, -0.2)
				var bottom_b = _ground(b, height_at, -0.2)
				var top_a = Vector3(a.x, eaves, a.y)
				var top_b = Vector3(b.x, eaves, b.y)
				_triangle(walls, bottom_a, top_a, bottom_b, wall_color)
				_triangle(walls, bottom_b, top_a, top_b, wall_color)
			var bounds = _bounds(footprint)
			var pitched = str(building.get("roof_shape", "flat")) in ["gabled", "hipped", "pyramidal", "half-hipped"]
			_roof(roofs, footprint, eaves, bounds, pitched, roof_color)
			var expanded = Geometry2D.offset_polygon(footprint, 7.0)
			for blocked in expanded:
				_index(bins, _bounds(blocked), {"polygon": blocked})
			drawn = true
		if drawn:
			count += 1
	_finish(parent, walls, _material(Color.WHITE, true), "MappedFootprintWalls")
	_finish(parent, roofs, _material(Color.WHITE, true), "MappedFootprintRoofs")
	return count

static func _roof(surface: SurfaceTool, polygon: PackedVector2Array, eaves: float, bounds: Rect2, pitched: bool, color: Color) -> void:
	var pieces: Array[PackedVector2Array] = [polygon]
	var short_x = bounds.size.x < bounds.size.y
	var span = bounds.size.x if short_x else bounds.size.y
	var middle = bounds.get_center().x if short_x else bounds.get_center().y
	var rise = minf(span * 0.23, 4.0) if pitched else 0.0
	if pitched and span > 0.1:
		pieces.clear()
		for side in range(2):
			var rect = bounds.grow(0.1)
			if short_x:
				rect.position.x = bounds.position.x - 0.1 if side == 0 else middle
				rect.size.x = span * 0.5 + 0.1
			else:
				rect.position.y = bounds.position.y - 0.1 if side == 0 else middle
				rect.size.y = span * 0.5 + 0.1
			var cutter = PackedVector2Array([rect.position, Vector2(rect.end.x, rect.position.y), rect.end, Vector2(rect.position.x, rect.end.y)])
			pieces.append_array(Geometry2D.intersect_polygons(polygon, cutter))
	# Close the gable above the wall wherever a footprint edge crosses the ridge.
	if pitched:
		for index in range(polygon.size()):
			var a = polygon[index]
			var b = polygon[(index + 1) % polygon.size()]
			var axis_a = a.x if short_x else a.y
			var axis_b = b.x if short_x else b.y
			var edge: Array[Vector2] = [a]
			if (axis_a - middle) * (axis_b - middle) < 0.0:
				edge.append(a.lerp(b, (middle - axis_a) / (axis_b - axis_a)))
			edge.append(b)
			for part in range(edge.size() - 1):
				var bottom_a = Vector3(edge[part].x, eaves, edge[part].y)
				var bottom_b = Vector3(edge[part + 1].x, eaves, edge[part + 1].y)
				var coordinate_a = edge[part].x if short_x else edge[part].y
				var coordinate_b = edge[part + 1].x if short_x else edge[part + 1].y
				var top_a = bottom_a + Vector3.UP * rise * maxf(0.0, 1.0 - absf(coordinate_a - middle) / maxf(0.05, span * 0.5))
				var top_b = bottom_b + Vector3.UP * rise * maxf(0.0, 1.0 - absf(coordinate_b - middle) / maxf(0.05, span * 0.5))
				_triangle(surface, bottom_a, top_a, bottom_b, color)
				_triangle(surface, bottom_b, top_a, top_b, color)
	for piece in pieces:
		var indices = Geometry2D.triangulate_polygon(piece)
		for index in range(0, indices.size(), 3):
			var points: Array[Vector3] = []
			for offset in range(3):
				var point = piece[indices[index + offset]]
				var axis = point.x if short_x else point.y
				var y = eaves + 0.03 + rise * maxf(0.0, 1.0 - absf(axis - middle) / maxf(0.05, span * 0.5))
				points.append(Vector3(point.x, y, point.y))
			_triangle(surface, points[0], points[2], points[1], color)

static func _forest(parent: Node3D, cover: Image, height_at: Callable, extent: float, site: PackedVector2Array, bins: Dictionary) -> int:
	if cover == null or cover.is_empty():
		return 0
	var rng = RandomNumberGenerator.new()
	rng.seed = 20211031
	var trees: Array[Vector2] = []
	var candidates = 0
	var cells = ceili(extent / TREE_SPACING)
	# Reservoir sampling keeps the cap spatially unbiased across the full map.
	for row in range(cells):
		for column in range(cells):
			var point = Vector2((column + rng.randf_range(0.12, 0.88)) * TREE_SPACING, (row + rng.randf_range(0.12, 0.88)) * TREE_SPACING) - Vector2.ONE * extent * 0.5
			if absf(point.x) >= extent * 0.5 or absf(point.y) >= extent * 0.5:
				continue
			var uv = (point / extent + Vector2.ONE * 0.5) * Vector2(cover.get_width(), cover.get_height())
			var color = cover.get_pixel(clampi(int(uv.x), 0, cover.get_width() - 1), clampi(int(uv.y), 0, cover.get_height() - 1))
			if color.r > 0.025 or absf(color.g - 100.0 / 255.0) > 0.025 or color.b > 0.025 or color.a < 0.5:
				continue
			if _inside(point, site) or _blocked(point, bins):
				continue
			# Keep whole crowns clear of the graded site, not only their trunks.
			var clear = true
			for edge in range(site.size()):
				if point.distance_squared_to(Geometry2D.get_closest_point_to_segment(point, site[edge], site[(edge + 1) % site.size()])) < 64.0:
					clear = false
					break
			if not clear:
				continue
			candidates += 1
			if trees.size() < TREE_LIMIT:
				trees.append(point)
			else:
				var slot = rng.randi_range(0, candidates - 1)
				if slot < TREE_LIMIT:
					trees[slot] = point
	var chunks: Dictionary = {}
	for point in trees:
		var species = rng.randi_range(0, 3)
		var key = Vector3i(floori(point.x / CHUNK_SIZE), floori(point.y / CHUNK_SIZE), species)
		if not chunks.has(key):
			chunks[key] = []
		var height = rng.randf_range(8.0, 20.0)
		var radius = rng.randf_range(4.0, 8.0)
		var basis = Basis(Vector3.UP, rng.randf_range(-PI, PI)).scaled(Vector3(radius / 0.4, height, radius / 0.4))
		var origin = Vector3(key.x * CHUNK_SIZE, 0, key.y * CHUNK_SIZE)
		chunks[key].append(Transform3D(basis, _ground(point, height_at) - origin))
	var meshes: Array[ArrayMesh] = []
	for species in range(4):
		meshes.append(_tree_mesh(species))
	var material = _material(Color.WHITE, true)
	for key in chunks:
		var transforms: Array = chunks[key]
		var multimesh = MultiMesh.new()
		multimesh.transform_format = MultiMesh.TRANSFORM_3D
		multimesh.use_colors = true
		multimesh.mesh = meshes[key.z]
		multimesh.instance_count = transforms.size()
		for index in range(transforms.size()):
			multimesh.set_instance_transform(index, transforms[index])
			var shade = rng.randf_range(0.8, 1.12)
			multimesh.set_instance_color(index, Color(shade * rng.randf_range(0.92, 1.05), shade, shade * rng.randf_range(0.9, 1.06)))
		var node = MultiMeshInstance3D.new()
		node.name = "Trees_%s_%s_%s" % [key.x, key.y, key.z]
		node.position = Vector3(key.x * CHUNK_SIZE, 0, key.y * CHUNK_SIZE)
		node.multimesh = multimesh
		node.material_override = material
		parent.add_child(node)
	parent.set_meta("eligible_samples", candidates)
	parent.set_meta("chunk_size_m", CHUNK_SIZE)
	return trees.size()

static func _tree_mesh(species: int) -> ArrayMesh:
	var surface = _surface()
	var rng = RandomNumberGenerator.new()
	rng.seed = 891 + species
	# A trunk and overlapping irregular crown lobes share one draw surface.
	_lobe(surface, Vector3(0, 0.2, 0), Vector3(0.022, 0.23, 0.022), Color("554c3d"), rng)
	var colors = [Color("425534"), Color("526341"), Color("354e35"), Color("314e3b")]
	if species == 3:
		for layer in range(4):
			var y = 0.30 + layer * 0.14
			var radius = 0.36 - layer * 0.065
			for side in range(9):
				var angle = side * TAU / 9.0
				var next = (side + 1) * TAU / 9.0
				var a = Vector3(cos(angle) * radius, y + rng.randf_range(-0.04, 0.04), sin(angle) * radius)
				var b = Vector3(cos(next) * radius, y + rng.randf_range(-0.04, 0.04), sin(next) * radius)
				_triangle(surface, a, Vector3(0.025, y + 0.29, 0), b, colors[species] * rng.randf_range(0.85, 1.1))
	else:
		for lobe in range(5):
			var angle = lobe * TAU / 4.0 + species
			var center = Vector3(cos(angle) * 0.16, rng.randf_range(0.52, 0.70), sin(angle) * 0.16)
			if lobe == 4:
				center = Vector3(0.0, 0.79, 0.0)
			_lobe(surface, center, Vector3(0.24, rng.randf_range(0.20, 0.28), 0.24), colors[species] * rng.randf_range(0.9, 1.08), rng)
	return surface.commit()

static func _lobe(surface: SurfaceTool, center: Vector3, scale: Vector3, color: Color, rng: RandomNumberGenerator) -> void:
	var rings: Array[Vector3] = []
	for row in range(5):
		var latitude = PI * row / 4.0
		for column in range(7):
			var angle = column * TAU / 7.0
			var radius = sin(latitude) * rng.randf_range(0.87, 1.1)
			rings.append(center + Vector3(cos(angle) * radius, cos(latitude), sin(angle) * radius) * scale)
	for row in range(4):
		for column in range(7):
			var a = row * 7 + column
			var b = row * 7 + (column + 1) % 7
			if row > 0:
				_triangle(surface, rings[a], rings[b], rings[a + 7], color)
			if row < 3:
				_triangle(surface, rings[b], rings[b + 7], rings[a + 7], color)
