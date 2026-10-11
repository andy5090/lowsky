extends Node3D
## Reference lines (MDL and DMZ limits) plus author-only launch areas.
## Lines come from Natural Earth 1:10m (generalized by hundreds of metres); launch
## areas are scenario planning assumptions. Local metres: X east, Z south.

const UIText = preload("res://ui_text.gd")

const LINE_STYLES = {
	"mdl": {"color": Color("ff4f45"), "half_width_m": 60.0, "min_half_pixels": 3.0, "dash_m": 0.0, "gap_m": 0.0, "short": {"en": "MDL", "ko": "군사분계선"}, "label_x": [-26000.0, -4000.0, 34000.0]},
	"dmz_south": {"color": Color("ffb547"), "half_width_m": 40.0, "min_half_pixels": 2.0, "dash_m": 1400.0, "gap_m": 900.0, "short": {"en": "DMZ south limit", "ko": "남방한계선"}, "label_x": [-8000.0, 20000.0]},
	"dmz_north": {"color": Color("ffb547"), "half_width_m": 40.0, "min_half_pixels": 2.0, "dash_m": 1400.0, "gap_m": 900.0, "short": {"en": "DMZ north limit", "ko": "북방한계선"}, "label_x": [-32000.0, 44000.0]},
}
## Lift above the supplied ground so ribbons never depth-fight the terrain.
const LINE_LIFT_M = 4.0
const AUTHOR_COLOR = Color("edb0fb")
const RIBBON_SHADER = """shader_type spatial;
render_mode unshaded, cull_disabled, fog_disabled, shadows_disabled;
uniform vec4 line_color : source_color;
uniform float half_width_m = 50.0;
uniform float min_half_pixels = 1.5;
uniform float dash_m = 0.0;
uniform float gap_m = 0.0;
void vertex() {
	// UV2 is the signed horizontal side vector. Widen far away so the line keeps a
	// legible screen width from the approach overview down to close views.
	vec4 view = MODELVIEW_MATRIX * vec4(VERTEX, 1.0);
	float depth = PROJECTION_MATRIX[3][3] > 0.5 ? 1.0 : max(-view.z, 1.0);
	float metres_per_pixel = 2.0 * depth / (VIEWPORT_SIZE.y * PROJECTION_MATRIX[1][1]);
	VERTEX.xz += UV2 * max(half_width_m, min_half_pixels * metres_per_pixel);
}
void fragment() {
	if (dash_m > 0.0 && mod(UV.x, dash_m + gap_m) > dash_m) {
		discard;
	}
	ALBEDO = line_color.rgb;
}
"""

var line_data: Dictionary = {}
var corridors: Array = []
var ribbons: Dictionary = {}
var line_labels: Array = []
var launch_root: Node3D

func build(mdl: Dictionary, corridor_data: Dictionary, ground_height: Callable) -> void:
	line_data = mdl.get("lines", {})
	corridors = corridor_data.get("corridors", [])
	var shader = Shader.new()
	shader.code = RIBBON_SHADER
	for id in LINE_STYLES:
		if not line_data.has(id):
			continue
		var style: Dictionary = LINE_STYLES[id]
		var ribbon = MeshInstance3D.new()
		ribbon.name = "Line_" + id
		var material = ShaderMaterial.new()
		material.shader = shader
		material.set_shader_parameter("line_color", style.color)
		for parameter in ["half_width_m", "min_half_pixels", "dash_m", "gap_m"]:
			material.set_shader_parameter(parameter, style[parameter])
		ribbon.material_override = material
		ribbon.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		# The shader widens vertices beyond the mesh AABB at long range.
		ribbon.extra_cull_margin = 4000.0
		add_child(ribbon)
		ribbons[id] = ribbon
		# Compact names keep markers legible from the approach view; the data file's
		# full label is kept on each marker as metadata.
		var label: Dictionary = line_data[id].get("label", {})
		for x in style.label_x:
			var marker = Label3D.new()
			marker.name = "Label_%s_%d" % [id, line_labels.size()]
			marker.set_meta("full_label", label)
			marker.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			marker.fixed_size = true
			marker.no_depth_test = true
			marker.font_size = 24
			marker.pixel_size = 0.0008
			marker.outline_size = 8
			marker.modulate = style.color.lightened(0.25)
			marker.set_meta("line_id", id)
			marker.set_meta("x", x)
			add_child(marker)
			line_labels.append(marker)
	launch_root = Node3D.new()
	launch_root.name = "LaunchAreas"
	launch_root.visible = false
	add_child(launch_root)
	var disc_material = StandardMaterial3D.new()
	disc_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	disc_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	disc_material.disable_fog = true
	disc_material.albedo_color = Color(AUTHOR_COLOR, 0.6)
	for corridor in corridors:
		var marker = Node3D.new()
		marker.name = "Launch_" + str(corridor.id)
		marker.set_meta("launch", Vector3(corridor.launch[0], corridor.launch[1], corridor.launch[2]))
		var disc = MeshInstance3D.new()
		disc.name = "Area"
		var mesh = CylinderMesh.new()
		mesh.top_radius = 600.0
		mesh.bottom_radius = 600.0
		mesh.height = 2.0
		mesh.radial_segments = 48
		disc.mesh = mesh
		disc.material_override = disc_material
		disc.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		marker.add_child(disc)
		var label = Label3D.new()
		label.name = "Label"
		label.set_meta("title", corridor.get("label", {}))
		label.set_meta("corridor_id", str(corridor.id))
		label.position.y = 120.0
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.fixed_size = true
		label.no_depth_test = true
		label.font_size = 22
		label.pixel_size = 0.0008
		# Three-level stagger keeps neighbouring corridor labels apart in the far view.
		label.offset.y = 68.0 * (launch_root.get_child_count() % 3)
		label.outline_size = 8
		label.modulate = AUTHOR_COLOR
		marker.add_child(label)
		launch_root.add_child(marker)
	reground(ground_height)
	apply_language()

func apply_language() -> void:
	for marker in line_labels:
		marker.text = UIText.pick(LINE_STYLES[marker.get_meta("line_id")].short)
	for marker in launch_root.get_children():
		var label: Label3D = marker.get_node("Label")
		label.text = UIText.t("geo.launch", [UIText.pick(label.get_meta("title"), label.get_meta("corridor_id"))])

func reground(ground_height: Callable) -> void:
	for id in ribbons:
		ribbons[id].mesh = ribbon_mesh(line_data[id].parts, ground_height)
	for label in line_labels:
		var point = point_at_x(line_data[label.get_meta("line_id")].parts, label.get_meta("x"))
		label.position = Vector3(point.x, float(ground_height.call(point.x, point.y)) + LINE_LIFT_M + 40.0, point.y)
	for marker in launch_root.get_children():
		var launch: Vector3 = marker.get_meta("launch")
		marker.position = Vector3(launch.x, float(ground_height.call(launch.x, launch.z)) + LINE_LIFT_M, launch.z)

func set_author_view(enabled: bool) -> void:
	# Launch areas are author knowledge; reference lines stay on in every view.
	launch_root.visible = enabled

static func ribbon_mesh(parts: Array, ground_height: Callable) -> ArrayMesh:
	var surface = SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var base = 0
	for part in parts:
		var points: Array = part.local
		if points.size() < 2:
			continue
		var distance = 0.0
		for index in points.size():
			var point = Vector2(points[index][0], points[index][1])
			if index > 0:
				distance += point.distance_to(Vector2(points[index - 1][0], points[index - 1][1]))
			var previous = Vector2(points[maxi(index - 1, 0)][0], points[maxi(index - 1, 0)][1])
			var following = Vector2(points[mini(index + 1, points.size() - 1)][0], points[mini(index + 1, points.size() - 1)][1])
			var direction = (following - previous).normalized()
			var side = Vector2(-direction.y, direction.x)
			var y = float(ground_height.call(point.x, point.y)) + LINE_LIFT_M
			for side_sign in [-1.0, 1.0]:
				surface.set_uv(Vector2(distance, side_sign))
				surface.set_uv2(side * side_sign)
				surface.add_vertex(Vector3(point.x, y, point.y))
		for index in points.size() - 1:
			var corner = base + index * 2
			for vertex in [corner, corner + 1, corner + 2, corner + 1, corner + 3, corner + 2]:
				surface.add_index(vertex)
		base += points.size() * 2
	return surface.commit()

static func point_at_x(parts: Array, x: float) -> Vector2:
	# Label anchor on the line at a chosen easting; nearest vertex if none spans it.
	var nearest = Vector2.INF
	for part in parts:
		var points: Array = part.local
		for index in points.size():
			var a = Vector2(points[index][0], points[index][1])
			if absf(a.x - x) < absf(nearest.x - x):
				nearest = a
			if index + 1 < points.size():
				var b = Vector2(points[index + 1][0], points[index + 1][1])
				if (a.x - x) * (b.x - x) <= 0.0 and a.x != b.x:
					return a.lerp(b, (x - a.x) / (b.x - a.x))
	return nearest
