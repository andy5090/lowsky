extends RefCounted
## Meter-scale, fictional display geometry. Not a surveyed or operational site.

const Detailed = preload("res://detailed_environment.gd")

static func vector(values: Array) -> Vector3:
	return Vector3(values[0], values[1], values[2])

static func make(layout: Dictionary, materials: Dictionary) -> Node3D:
	var root = Node3D.new()
	root.name = "SiteInfrastructure"
	root.set_meta("unit", "meter")
	var runway: Dictionary = layout.runway
	var center = vector(runway.center)
	var width = float(runway.width_m)
	var length = float(runway.length_m)
	var pavement = Detailed.box(root, Vector3(width, 0.16, length), center + Vector3(0, 0.06, 0), materials.asphalt)
	pavement.name = "Runway"
	pavement.set_meta("width_m", width)
	pavement.set_meta("length_m", length)
	var paint = StandardMaterial3D.new()
	paint.albedo_color = Color("e7e7dd")
	paint.roughness = 1.0
	# Each mark is constructed in meters; no scaling of the old miniature runway.
	var marks = Node3D.new()
	marks.name = "RunwayMarkings"
	root.add_child(marks)
	for side in [-1, 1]:
		Detailed.box(marks, Vector3(0.45, 0.025, length - 12), center + Vector3(side * (width * 0.5 - 1.0), 0.155, 0), paint)
		for stripe in range(8):
			var x = (stripe - 3.5) * 3.8
			Detailed.box(marks, Vector3(1.7, 0.025, 30), center + Vector3(x, 0.155, side * (length * 0.5 - 30)), paint)
	for index in range(floori((length - 140) / 60)):
		Detailed.box(marks, Vector3(0.9, 0.025, 30), center + Vector3(0, 0.155, -length * 0.5 + 85 + index * 60), paint)
	var apron: Dictionary = layout.apron
	var apron_center = vector(apron.center)
	var apron_surface = Detailed.box(root, Vector3(apron.width_m, 0.12, apron.length_m), apron_center + Vector3(0, 0.04, 0), materials.concrete)
	apron_surface.name = "Apron"
	# A simple visual connecting strip, not a taxi routing simulation.
	var strip_start = center.x + width * 0.5
	var strip_end = apron_center.x - float(apron.width_m) * 0.5
	var strip = Detailed.box(root, Vector3(absf(strip_end - strip_start), 0.12, 23), Vector3((strip_start + strip_end) * 0.5, 0.04, apron_center.z), materials.asphalt)
	strip.name = "ApronConnection"
	add_perimeter(root, layout.perimeter, materials)
	return root

static func instances(root: Node3D, node_name: String, mesh: Mesh, transforms: Array[Transform3D], material: Material) -> MultiMeshInstance3D:
	var multimesh = MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.mesh = mesh
	multimesh.instance_count = transforms.size()
	for index in range(transforms.size()):
		multimesh.set_instance_transform(index, transforms[index])
	var node = MultiMeshInstance3D.new()
	node.name = node_name
	node.multimesh = multimesh
	node.material_override = material
	root.add_child(node)
	return node

static func add_perimeter(root: Node3D, perimeter: Dictionary, materials: Dictionary) -> void:
	var fence = Node3D.new()
	fence.name = "PerimeterFence"
	root.add_child(fence)
	var width = float(perimeter.width_m)
	var length = float(perimeter.length_m)
	var height = float(perimeter.height_m)
	fence.set_meta("width_m", width)
	fence.set_meta("length_m", length)
	fence.set_meta("height_m", height)
	fence.set_meta("perimeter_m", 2 * (width + length))
	var corners: Array[Vector3] = [Vector3(-width / 2, 0, -length / 2), Vector3(width / 2, 0, -length / 2), Vector3(width / 2, 0, length / 2), Vector3(-width / 2, 0, length / 2)]
	var posts: Array[Transform3D] = []
	var panels: Array[Transform3D] = []
	var edge_material = StandardMaterial3D.new()
	edge_material.albedo_color = Color("b4aa8e")
	edge_material.roughness = 1.0
	for side in range(4):
		var start = corners[side]
		var end = corners[(side + 1) % 4]
		var direction = (end - start).normalized()
		var side_length = start.distance_to(end)
		var segments = ceili(side_length / 10.0)
		var step = side_length / segments
		var center = (start + end) * 0.5
		# The four-meter ground strip keeps the boundary readable in the overview.
		var edge = Detailed.box(fence, Vector3(side_length, 0.05, 4), center + Vector3(0, 0.025, 0), edge_material)
		edge.rotation.y = -atan2(direction.z, direction.x)
		edge.name = "BoundaryEdge%d" % side
		for level in [0.3, height * 0.5, height - 0.08]:
			var rail = Detailed.box(fence, Vector3(side_length, 0.045, 0.045), center + Vector3(0, level, 0), materials.dark_metal)
			rail.rotation.y = edge.rotation.y
		for index in range(segments):
			posts.append(Transform3D(Basis.IDENTITY, start + direction * index * step + Vector3(0, height / 2, 0)))
			var basis = Basis(direction * step, Vector3.UP * height, direction.cross(Vector3.UP))
			panels.append(Transform3D(basis, start + direction * (index + 0.5) * step + Vector3(0, height / 2, 0)))
	var post_mesh = BoxMesh.new()
	post_mesh.size = Vector3(0.12, height, 0.12)
	instances(fence, "Posts", post_mesh, posts, materials.dark_metal)
	# Shared quad panels render a fine open mesh without tens of thousands of nodes.
	var mesh_shader = Shader.new()
	mesh_shader.code = """
shader_type spatial;
render_mode cull_disabled;
void fragment() {
	vec2 grid = abs(fract(UV * vec2(40.0, 10.0)) - vec2(0.5));
	float wire = max(step(0.475, grid.x), step(0.475, grid.y));
	ALBEDO = vec3(0.28, 0.31, 0.29);
	ROUGHNESS = 0.8;
	ALPHA = wire;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
}
"""
	var mesh_material = ShaderMaterial.new()
	mesh_material.shader = mesh_shader
	var panel_mesh = QuadMesh.new()
	panel_mesh.size = Vector2.ONE
	var mesh_node = instances(fence, "WireMesh", panel_mesh, panels, mesh_material)
	mesh_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	fence.set_meta("post_count", posts.size())
	fence.set_meta("panel_count", panels.size())
