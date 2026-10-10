extends Node3D
## Local fixture viewer. Author view is explicitly separate from agent input.

const Detailed = preload("res://detailed_environment.gd")
const Geographic = preload("res://geographic_environment.gd")
const Site = preload("res://site_environment.gd")
const DroneOverlay = preload("res://drone_overlay.gd")
const Plains = preload("res://plains_environment.gd")

var data_root = ProjectSettings.globalize_path("res://").path_join("../data/scenarios/v1")
var objects: Array = []
var public_data: Dictionary = {}
var world_data: Dictionary = {}
var camera: Camera3D
var status_label: Label
var time_label: Label
var elapsed_ms = 0.0
var playing = true
var case_id = "case_001"
var use_external_assets = true
var realistic = true
var plains_test = true
var geographic = true
var terrain_data: Dictionary = {}
var terrain: Node3D
var field_installations: Dictionary = {}
var terrain_button: Button
var materials: Dictionary = {}
var display_profiles: Dictionary = {}
var site_layout: Dictionary = {}
var camera_target = Vector3.ZERO
var monitor_mode = false
var monitor_base_url = "http://127.0.0.1:8765"
var monitor_connected = false
var monitor_request: HTTPRequest
var monitor_clock = 0.0
var monitor_received_at = 0
var monitor_speed = 1.0
var monitor_playing = false
var drag_button = MOUSE_BUTTON_NONE
var drag_orbit = false
var follow_drone = false
var follow_button: Button
var drone_overlay: Control

func solid_material(color: Color, metallic: float = 0.0, roughness: float = 0.8) -> StandardMaterial3D:
	var material = StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic
	material.roughness = roughness
	return material

func pbr_material(asset: String, repeat_scale: float) -> StandardMaterial3D:
	var material = StandardMaterial3D.new()
	var path = "res://third_party/realistic/%s/" % asset
	material.albedo_texture = load(path + "albedo.jpg")
	material.normal_enabled = true
	material.normal_texture = load(path + "normal.jpg")
	material.normal_scale = 0.22
	var arm = load(path + "arm.jpg")
	material.roughness_texture = arm
	material.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	material.metallic_texture = arm
	material.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE
	material.metallic = 0.3 if asset == "corrugated_iron" else 0.0
	material.roughness = 1.0
	material.metallic_specular = 0.25
	material.ao_enabled = true
	material.ao_texture = arm
	material.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	material.uv1_triplanar = true
	material.uv1_world_triplanar = true
	material.uv1_scale = Vector3.ONE * repeat_scale
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return material

func build_materials() -> void:
	materials = {
		"concrete": pbr_material("hangar_concrete_floor", 0.3),
		"metal": pbr_material("corrugated_iron", 0.65),
		"grass": pbr_material("aerial_grass_rock", 0.05),
		"asphalt": pbr_material("asphalt_02", 0.25),
		"dark_metal": solid_material(Color("333b3c"), 0.6, 0.35),
		"painted_metal": solid_material(Color("879594"), 0.45, 0.55),
		"glass": solid_material(Color("233e47"), 0.7, 0.15)
	}
	materials.grass.albedo_color = Color("9dada0")
	materials.asphalt.albedo_color = Color("737b82")
	materials.metal.albedo_color = Color("7b858e")

func set_surface_material(node: Node, part_name: String, material: Material) -> void:
	if node is MeshInstance3D and node.name == part_name:
		node.material_override = material
	for child in node.get_children():
		set_surface_material(child, part_name, material)

func read_json(path: String) -> Dictionary:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	assert(parsed is Dictionary, "Invalid JSON: " + path)
	return parsed

func vector(values: Array) -> Vector3:
	return Vector3(values[0], values[1], values[2])

func asset_instance(asset_id: String, size_profile: String = "") -> Node3D:
	if asset_id == "phone_sensor_pole":
		return Detailed.make_phone_sensor_pole(materials)
	if realistic:
		match asset_id:
			"ground_tile":
				if geographic:
					return Geographic.make(terrain_data, materials.grass, site_layout)
				return Plains.make(materials.grass, site_layout) if plains_test else Detailed.make_terrain(materials.grass, site_layout)
			"hangar": return Detailed.make_hangar(materials)
			"arched_hangar": return Detailed.make_arched_hangar(materials)
			"control_tower": return Detailed.make_tower(materials)
			"utility_building": return Detailed.make_utility_building(materials)
			"office_building": return Detailed.make_office_building(materials)
			"service_building": return Detailed.make_service_building(materials)
	# Existing low-detail resources remain the fallback for each procedural variant.
	asset_id = {"arched_hangar": "hangar", "office_building": "utility_building", "service_building": "utility_building"}.get(asset_id, asset_id)
	var replacements = {"hangar": ["building-k", 10.0], "utility_building": ["building-h", 6.0]}
	var path = "res://assets/%s.glb" % asset_id
	if use_external_assets and asset_id in replacements:
		path = "res://third_party/kenney_industrial/%s.glb" % replacements[asset_id][0]
	var packed = load(path) as PackedScene
	assert(packed != null, "Missing asset: " + asset_id)
	var instance = packed.instantiate() as Node3D
	if asset_id == "aerial_marker":
		var profile_id = size_profile if not size_profile.is_empty() else str(display_profiles.default_drone_profile)
		assert(profile_id in display_profiles.profiles, "Unknown drone size profile: " + profile_id)
		var profile: Dictionary = display_profiles.profiles[profile_id]
		var bounds = collect_bounds(instance, Transform3D.IDENTITY)
		assert(not bounds.is_empty(), "Drone model has no mesh")
		var combined: AABB = bounds[0]
		for bound in bounds:
			combined = combined.merge(bound)
		var span = maxf(combined.size.x, combined.size.z)
		var target_span = float(profile.horizontal_span_m) * float(display_profiles.display_units_per_meter)
		assert(span > 0 and target_span > 0, "Invalid drone dimensions")
		var factor = target_span / span
		instance.scale *= factor
		instance.position = -combined.get_center() * factor
		var wrapper = Node3D.new()
		wrapper.name = "DroneDisplay"
		wrapper.set_meta("size_profile", profile_id)
		wrapper.add_child(instance)
		return wrapper
	if realistic and asset_id == "runway":
		set_surface_material(instance, "Surface", materials.asphalt)
	if use_external_assets and asset_id in replacements:
		var bounds = collect_bounds(instance, Transform3D.IDENTITY)
		assert(not bounds.is_empty(), "Imported asset has no mesh")
		var combined: AABB = bounds[0]
		for bound in bounds:
			combined = combined.merge(bound)
		var factor: float = replacements[asset_id][1] / combined.size.x
		instance.scale = Vector3.ONE * factor
		instance.position = -Vector3(combined.get_center().x, combined.position.y, combined.get_center().z) * factor
		var wrapper = Node3D.new()
		wrapper.add_child(instance)
		return wrapper
	return instance

func collect_bounds(node: Node3D, parent_transform: Transform3D) -> Array:
	var transform = parent_transform * node.transform
	var bounds: Array = []
	if node is MeshInstance3D and node.mesh:
		bounds.append(transform * node.mesh.get_aabb())
	for child in node.get_children():
		if child is Node3D:
			bounds.append_array(collect_bounds(child, transform))
	return bounds

func _ready() -> void:
	site_layout = read_json(data_root.path_join("../../site_layout.json"))
	camera_target = vector(site_layout.camera.target)
	monitor_mode = "--monitor" in OS.get_cmdline_user_args()
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--monitor-port="):
			var port = argument.trim_prefix("--monitor-port=")
			assert(port.is_valid_int() and int(port) > 0 and int(port) <= 65535)
			monitor_base_url = "http://127.0.0.1:%d" % int(port)
	display_profiles = read_json("res://assets/display_profiles.json")
	use_external_assets = not "--blockout" in OS.get_cmdline_user_args()
	realistic = use_external_assets and not "--stylized" in OS.get_cmdline_user_args()
	plains_test = not "--hills" in OS.get_cmdline_user_args()
	geographic = not ("--hills" in OS.get_cmdline_user_args() or "--plains" in OS.get_cmdline_user_args())
	terrain_data = read_json(data_root.path_join("../../terrain/korea_site.json"))
	build_materials()
	var environment = WorldEnvironment.new()
	var settings = Environment.new()
	if realistic:
		var sky = Sky.new()
		var sky_material = PanoramaSkyMaterial.new()
		sky_material.panorama = load("res://third_party/realistic/kloofendal_48d_partly_cloudy_puresky/sky.hdr")
		sky.sky_material = sky_material
		settings.sky = sky
		settings.background_mode = Environment.BG_SKY
		settings.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
		settings.tonemap_mode = Environment.TONE_MAPPER_FILMIC
		settings.ambient_light_energy = 0.7
		settings.fog_enabled = true
		settings.fog_light_color = Color("9dabb3")
		settings.fog_density = 0.000035
		settings.fog_sky_affect = 0.15
	else:
		settings.background_mode = Environment.BG_COLOR
		settings.background_color = Color("17252b")
		settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		settings.ambient_light_color = Color("b4d0d4")
		settings.ambient_light_energy = 0.65
	environment.environment = settings
	add_child(environment)
	var sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-32, -35, 0)
	sun.light_color = Color("fff0db")
	sun.light_energy = 1.0
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 160
	add_child(sun)
	camera = Camera3D.new()
	if realistic:
		camera.projection = Camera3D.PROJECTION_PERSPECTIVE
		camera.fov = 48
		camera.position = vector(site_layout.camera.close)
		camera.far = 18000
	else:
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 5200
		camera.position = vector(site_layout.camera.overview)
		camera.far = 18000
	add_child(camera)
	camera.look_at(camera_target)
	for placement in read_json(data_root.path_join("scene.json"))["environment"]:
		var instance = asset_instance(placement["asset_id"])
		instance.position = vector(placement["position"])
		instance.scale *= vector(placement.get("scale", [1, 1, 1]))
		add_child(instance)
		if placement.get("ground_to_terrain", false):
			instance.name = placement.id
			field_installations[placement.id] = {"node": instance, "position": vector(placement.position)}
		if placement["asset_id"] == "ground_tile":
			terrain = instance
	add_child(Site.make(site_layout, materials))
	ground_field_installations()
	if realistic:
		add_realistic_details()
	build_ui()
	load_case("case_001")
	if monitor_mode:
		show_overview()
		start_monitor()
	if "--capture" in OS.get_cmdline_user_args():
		playing = false
		elapsed_ms = 65000
		if "--overview" in OS.get_cmdline_user_args():
			camera.position = vector(site_layout.camera.overview)
			camera_target = Vector3.ZERO
			camera.look_at(camera_target)
		for frame in range(30):
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var filename = "asset-overview.png" if "--overview" in OS.get_cmdline_user_args() else "asset-preview.png"
		if realistic and plains_test:
			filename = "plains-overview.png" if "--overview" in OS.get_cmdline_user_args() else "plains-preview.png"
		if realistic and geographic:
			filename = "korea-overview.png" if "--overview" in OS.get_cmdline_user_args() else "korea-preview.png"
		var output = ProjectSettings.globalize_path("res://../artifacts/" + filename)
		DirAccess.make_dir_recursive_absolute(output.get_base_dir())
		var error = get_viewport().get_texture().get_image().save_png(output)
		print("Screenshot saved: %s (%s)" % [output, error])
		get_tree().quit(error)

func add_realistic_details() -> void:
	# Display-only aircraft; never observation evidence.
	var aircraft = (load("res://third_party/realistic/cesium_air/Cesium_Air.glb") as PackedScene).instantiate()
	var bounds = collect_bounds(aircraft, Transform3D.IDENTITY)
	var combined: AABB = bounds[0]
	for bound in bounds:
		combined = combined.merge(bound)
	var factor = 10.0 / maxf(combined.size.x, combined.size.z)
	aircraft.scale = Vector3.ONE * factor
	aircraft.position = vector(site_layout.aircraft_position) - Vector3(combined.get_center().x, combined.position.y, combined.get_center().z) * factor
	add_child(aircraft)
	var credit = Label.new()
	credit.text = "FICTIONAL SITE  •  MATERIALS: POLY HAVEN  •  AIRCRAFT: CESIUM  •  KOREA TERRAIN: MAPZEN / USGS"
	credit.position = Vector2(26, 867)
	credit.add_theme_font_size_override("font_size", 12)
	var layer = CanvasLayer.new()
	layer.add_child(credit)
	add_child(layer)

func build_ui() -> void:
	var layer = CanvasLayer.new()
	add_child(layer)
	var panel = PanelContainer.new()
	panel.position = Vector2(30, 26)
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.025, 0.045, 0.06, 0.94)
	style.content_margin_left = 22
	style.content_margin_right = 22
	style.content_margin_top = 18
	style.content_margin_bottom = 18
	panel.add_theme_stylebox_override("panel", style)
	layer.add_child(panel)
	var column = VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	panel.add_child(column)
	drone_overlay = DroneOverlay.new()
	drone_overlay.camera = camera
	drone_overlay.objects = objects
	layer.add_child(drone_overlay)
	layer.move_child(drone_overlay, 0)
	var title = Label.new()
	title.text = "LOW SKY / SCENE LAB"
	title.add_theme_font_size_override("font_size", 24)
	column.add_child(title)
	var subtitle = Label.new()
	subtitle.text = "FICTIONAL AIRFIELD  /  AUTHOR VIEW\nPBR material study · synthetic scenario replay" if realistic else "ASSET STUDY  /  SYNTHETIC AUTHOR VIEW\nBuilding samples + procedural placeholders"
	subtitle.modulate = Color("91b6b8")
	column.add_child(subtitle)
	if realistic:
		terrain_button = Button.new()
		terrain_button.text = terrain_caption()
		terrain_button.pressed.connect(toggle_terrain)
		column.add_child(terrain_button)
	var buttons = HBoxContainer.new()
	column.add_child(buttons)
	for index in range(3):
		var button = Button.new()
		button.text = ["Consistent", "Conflicting", "Missing"][index]
		var id = "case_%03d" % (index + 1)
		button.pressed.connect(func(): load_case(id))
		button.disabled = monitor_mode
		buttons.add_child(button)
	var playback = Button.new()
	playback.text = "Pause / Resume  [Space]"
	playback.pressed.connect(func(): playing = not playing)
	playback.disabled = monitor_mode
	column.add_child(playback)
	follow_button = Button.new()
	follow_button.text = "Follow first drone  [F]"
	follow_button.pressed.connect(toggle_follow)
	column.add_child(follow_button)
	var aids = CheckButton.new()
	aids.text = "SIM markers (not sensor evidence)"
	aids.button_pressed = true
	aids.toggled.connect(func(enabled: bool): drone_overlay.visible = enabled)
	column.add_child(aids)
	time_label = Label.new()
	column.add_child(time_label)
	status_label = Label.new()
	status_label.add_theme_font_size_override("font_size", 16)
	column.add_child(status_label)
	var hint = Label.new()
	hint.text = "Left / Middle drag: pan\nRight / Shift+Left drag: orbit\nWheel: zoom   C: view   H: home\n1 / 2 / 3: branch   R: restart\nSynthetic observations. No LLM connected."
	if monitor_mode:
		hint.text = "Left / Middle: pan   Right: orbit\nWheel: zoom   C: view   H: home\nReplay control: %s\n3D author view · monitor shows observations\nF: follow drone / overview · Model span 0.6 m" % monitor_base_url
	hint.modulate = Color("91b6b8")
	column.add_child(hint)

func terrain_caption() -> String:
	if geographic:
		return "Terrain: Korea DEM / modified site  [T]"
	return "Terrain: Synthetic plains  [T]" if plains_test else "Terrain: Synthetic hills  [T]"

func terrain_surface_height(x: float, z: float) -> float:
	if not realistic:
		return 0.0
	# Sample the rendered triangles, so exterior fixtures follow every terrain mode
	# without duplicating the DEM interpolation or synthetic-noise formula.
	var surface: MeshInstance3D = terrain.get_child(0)
	var arrays = surface.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	for index in range(0, indices.size(), 3):
		var a = vertices[indices[index]]
		var b = vertices[indices[index + 1]]
		var c = vertices[indices[index + 2]]
		if x < minf(a.x, minf(b.x, c.x)) or x > maxf(a.x, maxf(b.x, c.x)) or z < minf(a.z, minf(b.z, c.z)) or z > maxf(a.z, maxf(b.z, c.z)):
			continue
		var hit = Geometry3D.ray_intersects_triangle(Vector3(x, 10000, z), Vector3.DOWN, a, b, c)
		if hit != null:
			return hit.y
	assert(false, "Field installation is outside the rendered terrain")
	return 0.0

func ground_field_installations() -> void:
	for item in field_installations.values():
		var position: Vector3 = item.position
		item.node.position = position + Vector3(0, terrain_surface_height(position.x, position.z), 0)
	for zone in site_layout.get("display_zones", []):
		if zone.get("ground_to_terrain", false):
			var position = vector(zone.position)
			get_node("SiteInfrastructure/DisplayZones/" + zone.id).position.y = position.y + 22 + terrain_surface_height(position.x, position.z)

func toggle_terrain() -> void:
	if not realistic:
		return
	if geographic:
		geographic = false
		plains_test = true
	elif plains_test:
		plains_test = false
	else:
		geographic = true
	remove_child(terrain)
	terrain.queue_free()
	terrain = asset_instance("ground_tile")
	add_child(terrain)
	ground_field_installations()
	terrain_button.text = terrain_caption()

func load_case(id: String) -> void:
	for item in objects:
		item["node"].queue_free()
	objects.clear()
	case_id = id
	world_data = read_json(data_root.path_join("cases/%s/world.json" % id))
	public_data = read_json(data_root.path_join("cases/%s/public.json" % id))
	for item in world_data["objects"]:
		var instance = asset_instance(item["visual"]["asset_id"], item["visual"].get("size_profile", ""))
		add_child(instance)
		var label = Label3D.new()
		label.text = item["object_id"]
		label.position.y = 0.7
		label.font_size = 40
		label.pixel_size = 0.015 if realistic else 0.03
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		instance.add_child(label)
		objects.append({"object_id": item.object_id, "node": instance, "keyframes": item["keyframes"]})
	elapsed_ms = 0

func _process(delta: float) -> void:
	camera.near = clampf(camera.position.distance_to(camera_target) * 0.02, 0.1, 50.0)
	if monitor_mode:
		var age = Time.get_ticks_msec() - monitor_received_at
		monitor_connected = monitor_connected and age <= 1500
		if monitor_connected:
			elapsed_ms = minf(monitor_clock + (minf(age, 500) * monitor_speed if monitor_playing else 0.0), float(world_data.duration_ms))
	elif playing:
		elapsed_ms = minf(elapsed_ms + delta * 1000, float(world_data.duration_ms))
	for item in objects:
		var frames = item["keyframes"]
		var index = 0
		while index < frames.size() - 2 and elapsed_ms >= float(frames[index + 1].at_ms):
			index += 1
		var interval = float(frames[index + 1].at_ms) - float(frames[index].at_ms)
		var ratio = clampf((elapsed_ms - float(frames[index].at_ms)) / interval, 0, 1)
		item["node"].position = vector(frames[index]["position"]).lerp(vector(frames[index + 1]["position"]), ratio)
	if follow_drone:
		update_follow_camera()
	if time_label:
		time_label.text = "%s  |  %03d / %03d s" % [case_id, elapsed_ms / 1000, int(world_data.duration_ms) / 1000]
		var lines = PackedStringArray()
		for source in public_data.get("source_ids", []):
			var state = "unknown"
			for event in public_data["source_health"]:
				if event["source_id"] == source and event["available_at_ms"] <= elapsed_ms:
					state = event["status"]
			lines.append("%s: %s" % [source, state])
		status_label.text = ("MONITOR: connected" if monitor_connected else "MONITOR: disconnected · replay frozen") if monitor_mode else "\n".join(lines)

func show_overview() -> void:
	stop_follow()
	camera_target = Vector3(0, 0, -300)
	camera.position = vector(site_layout.camera.overview)
	camera.size = 5200
	camera.look_at(camera_target)

func stop_follow() -> void:
	follow_drone = false
	if follow_button:
		follow_button.text = "Follow first drone  [F]"

func toggle_follow() -> void:
	if follow_drone:
		show_overview()
	elif not objects.is_empty():
		follow_drone = true
		follow_button.text = "Return to overview  [F]"
		update_follow_camera()

func update_follow_camera() -> void:
	if objects.is_empty():
		return
	camera_target = objects[0].node.position
	camera.position = camera_target + Vector3(4, 2.5, 6)
	camera.size = 5
	camera.near = 0.1
	camera.look_at(camera_target)

func pan_camera(relative: Vector2) -> void:
	stop_follow()
	var offset = camera.position - camera_target
	var span = camera.size if camera.projection == Camera3D.PROJECTION_ORTHOGONAL else 2.0 * offset.length() * tan(deg_to_rad(camera.fov * 0.5))
	var scale = span / maxf(get_viewport().get_visible_rect().size.y, 1)
	var right = Vector3(camera.basis.x.x, 0, camera.basis.x.z).normalized()
	var back = Vector3(camera.basis.z.x, 0, camera.basis.z.z).normalized()
	var movement = (-right * relative.x + back * relative.y / maxf(offset.normalized().y, 0.15)) * scale
	var target = camera_target + movement
	target.x = clampf(target.x, -6000, 6000)
	target.z = clampf(target.z, -6000, 6000)
	camera.position += target - camera_target
	camera_target = target

func orbit_camera(relative: Vector2) -> void:
	stop_follow()
	var offset = camera.position - camera_target
	var distance = offset.length()
	var yaw = atan2(offset.x, offset.z) - relative.x * 0.006
	var pitch = clampf(asin(offset.y / distance) + relative.y * 0.006, deg_to_rad(8), deg_to_rad(85))
	camera.position = camera_target + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	camera.look_at(camera_target)

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_WINDOW_FOCUS_OUT:
		drag_button = MOUSE_BUTTON_NONE

func _input(event: InputEvent) -> void:
	# A drag starts only outside the UI, but continues/releases across UI bounds.
	if drag_button == MOUSE_BUTTON_NONE:
		return
	if event is InputEventMouseButton and event.button_index == drag_button and not event.pressed:
		drag_button = MOUSE_BUTTON_NONE
		# Let the GUI clear its own pressed-button bookkeeping as well.
	elif event is InputEventMouseMotion:
		if not event.button_mask & (1 << (drag_button - 1)):
			drag_button = MOUSE_BUTTON_NONE
			return
		if drag_orbit:
			orbit_camera(event.relative)
		else:
			pan_camera(event.relative)
		get_viewport().set_input_as_handled()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if monitor_mode and event.keycode in [KEY_SPACE, KEY_R, KEY_1, KEY_2, KEY_3]:
			return
		match event.keycode:
			KEY_SPACE: playing = not playing
			KEY_R: elapsed_ms = 0
			KEY_1: load_case("case_001")
			KEY_2: load_case("case_002")
			KEY_3: load_case("case_003")
			KEY_T: toggle_terrain()
			KEY_F: toggle_follow()
			KEY_H:
				stop_follow()
				camera_target = vector(site_layout.camera.target)
				camera.position = vector(site_layout.camera.close)
				camera.size = 500
				camera.look_at(camera_target)
			KEY_C:
				stop_follow()
				if camera.position.y < 1000:
					camera_target = Vector3.ZERO
					camera.position = vector(site_layout.camera.overview)
					camera.size = 5200
				else:
					camera_target = vector(site_layout.camera.target)
					camera.position = vector(site_layout.camera.close)
					camera.size = 500
				camera.look_at(camera_target)
			KEY_LEFT, KEY_RIGHT:
				stop_follow()
				camera.position = camera_target + (camera.position - camera_target).rotated(Vector3.UP, 0.12 if event.keycode == KEY_LEFT else -0.12)
				camera.look_at(camera_target)
	if event is InputEventMouseButton and event.pressed:
		if event.button_index in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_RIGHT]:
			drag_button = event.button_index
			drag_orbit = event.button_index == MOUSE_BUTTON_RIGHT or (event.button_index == MOUSE_BUTTON_LEFT and event.shift_pressed)
			get_viewport().set_input_as_handled()
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			stop_follow()
			if realistic:
				camera.position = camera_target + (camera.position - camera_target).normalized() * maxf(18, camera.position.distance_to(camera_target) * 0.88)
			else:
				camera.size = maxf(40, camera.size * 0.88)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			stop_follow()
			if realistic:
				camera.position = camera_target + (camera.position - camera_target).normalized() * minf(10000, camera.position.distance_to(camera_target) * 1.12)
			else:
				camera.size = minf(12000, camera.size * 1.12)

func start_monitor() -> void:
	playing = false
	monitor_request = HTTPRequest.new()
	monitor_request.timeout = 1.0
	add_child(monitor_request)
	monitor_request.request_completed.connect(receive_monitor_clock)
	var timer = Timer.new()
	timer.wait_time = 0.25
	timer.timeout.connect(poll_monitor)
	add_child(timer)
	timer.start()
	poll_monitor()

func poll_monitor() -> void:
	if monitor_request.get_http_client_status() == HTTPClient.STATUS_DISCONNECTED:
		monitor_request.request(monitor_base_url + "/api/clock")

func receive_monitor_clock(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		monitor_connected = false
		return
	var state = JSON.parse_string(body.get_string_from_utf8())
	if not state is Dictionary or not state.has_all(["case_id", "at_ms", "playing", "speed"]):
		monitor_connected = false
		return
	var next_case = str(state.case_id)
	if not next_case.begins_with("case_") or not next_case.substr(5).is_valid_int():
		return
	if next_case != case_id:
		if not FileAccess.file_exists(data_root.path_join("cases/%s/world.json" % next_case)):
			return
		load_case(next_case)
	monitor_clock = float(state.at_ms)
	monitor_speed = float(state.speed)
	monitor_playing = bool(state.playing)
	monitor_received_at = Time.get_ticks_msec()
	monitor_connected = true
	elapsed_ms = monitor_clock
