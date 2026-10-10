extends Node3D
## Local fixture viewer. Author view is explicitly separate from agent input.

const Detailed = preload("res://detailed_environment.gd")
const Geographic = preload("res://geographic_environment.gd")
const Site = preload("res://site_environment.gd")
const DroneOverlay = preload("res://drone_overlay.gd")
const Plains = preload("res://plains_environment.gd")
const DroneModels = preload("res://drone_models.gd")
const SimulationUITheme = preload("res://simulation_ui_theme.gd")
const ExerciseUnits = preload("res://exercise_units.gd")

var data_root = ProjectSettings.globalize_path("res://").path_join("../data/scenarios/v1")
var objects: Array = []
var public_data: Dictionary = {}
var world_data: Dictionary = {}
var camera: Camera3D
var status_label: Label
var time_label: Label
var ui_panel: PanelContainer
var ui_body: VBoxContainer
var ui_scroll: ScrollContainer
var ui_title: Label
var ui_toggle: Button
var elapsed_ms = 0.0
var playing = true
var case_id = "case_001"
var use_external_assets = true
var realistic = true
var plains_test = true
var geographic = true
var terrain_data: Dictionary = {}
var geographic_context: Dictionary = {}
var terrain: Node3D
var field_installations: Dictionary = {}
var terrain_button: Button
var materials: Dictionary = {}
var display_profiles: Dictionary = {}
var site_layout: Dictionary = {}
var camera_target = Vector3.ZERO
var desktop_mode = false
var desktop_revision = -1
var desktop_state: Dictionary = {}
var desktop_poll_request: HTTPRequest
var desktop_command_request: HTTPRequest
var desktop_status: Label
var desktop_monitor_button: Button
var desktop_fullscreen_button: Button
var monitor_mode = false
var monitor_base_url = "http://127.0.0.1:8765"
var monitor_connected = false
var monitor_request: HTTPRequest
var monitor_clock = 0.0
var monitor_received_at = 0
var monitor_speed = 1.0
var monitor_playing = false
var monitor_test_run: Dictionary = {}
var monitor_exercise: Dictionary = {}
var monitor_tactics: Dictionary = {}
var tactics_targets: Dictionary = {}
var tactics_effector_labels: Dictionary = {}
var exercise_marker: Label3D
var simulation_missions: Array = []
var mission_nodes: Dictionary = {}
var facility_nodes: Dictionary = {}
var visual_cast_signature = ""
var exercise_units: Node3D
var drag_button = MOUSE_BUTTON_NONE
var drag_orbit = false
var follow_drone = false
var selected_drone_index = 0
var follow_button: Button
var previous_drone_button: Button
var next_drone_button: Button
var selected_drone_label: Label
var drone_overlay: Control
var show_drone_positions = false
var detected_ids: Dictionary = {}

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

func asset_instance(asset_id: String, size_profile: String = "", airframe_id: String = "") -> Node3D:
	if asset_id == "aerial_marker":
		return drone_instance(airframe_id, size_profile)
	if asset_id == "phone_sensor_pole":
		return Detailed.make_phone_sensor_pole(materials)
	if realistic:
		match asset_id:
			"ground_tile":
				if geographic:
					return Geographic.make(terrain_data, materials.grass, site_layout, geographic_context)
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

func drone_instance(airframe_id: String = "", size_profile: String = "") -> Node3D:
	var id = airframe_id if airframe_id in display_profiles.airframes else str(display_profiles.default_airframe)
	var airframe: Dictionary = display_profiles.airframes[id]
	var profile_id = size_profile if size_profile in display_profiles.profiles else str(airframe.size_profile)
	var instance: Node3D
	if not realistic:
		instance = (load("res://assets/aerial_marker.glb") as PackedScene).instantiate()
	elif airframe.model_id == "cesium_drone" and use_external_assets:
		instance = (load("res://third_party/realistic/cesium_drone/CesiumDrone.glb") as PackedScene).instantiate()
		instance.rotation.y = PI # Imported camera faces +Z; our airframes face -Z.
	else:
		instance = DroneModels.make("quadcopter" if airframe.model_id == "cesium_drone" else str(airframe.model_id))
	var bounds = collect_bounds(instance, Transform3D.IDENTITY)
	assert(not bounds.is_empty(), "Drone model has no mesh")
	var combined: AABB = bounds[0]
	for bound in bounds:
		combined = combined.merge(bound)
	var target_span = float(display_profiles.profiles[profile_id].horizontal_span_m) * float(display_profiles.display_units_per_meter)
	var factor = target_span / maxf(combined.size.x, combined.size.z)
	instance.scale *= factor
	instance.position = -combined.get_center() * factor
	var wrapper = Node3D.new()
	wrapper.name = "DroneDisplay"
	wrapper.set_meta("size_profile", profile_id)
	wrapper.set_meta("airframe_id", id)
	wrapper.set_meta("horizontal_span_m", target_span)
	var visual = Node3D.new()
	visual.name = "Visual"
	wrapper.add_child(visual)
	visual.add_child(instance)
	var rotors: Array = instance.get_meta("rotors", [])
	for rotor in rotors:
		rotor.set_meta("rest_basis", rotor.basis)
	wrapper.set_meta("rotors", rotors)
	var players = instance.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty():
		var player: AnimationPlayer = players[0]
		if player.has_animation("Fly"):
			player.play("Fly")
			player.pause()
			wrapper.set_meta("animation_player", player)
	return wrapper

func pose_drone(node: Node3D, direction: Vector3, time_ms: float) -> void:
	var visual = node.get_node("Visual") as Node3D
	if direction.length_squared() > 0.0001:
		visual.rotation.y = atan2(-direction.x, -direction.z)
	# Animation is cosmetic, driven by the shared clock and limited to close views.
	if camera.position.distance_squared_to(node.position) > 150.0 * 150.0:
		return
	var rotors: Array = node.get_meta("rotors", [])
	for index in rotors.size():
		var rotor: Node3D = rotors[index]
		rotor.basis = Basis(rotor.get_meta("axis", Vector3.UP), fmod(time_ms * 0.045 * (1 if index % 2 == 0 else -1), TAU)) * rotor.get_meta("rest_basis")
	var player = node.get_meta("animation_player") as AnimationPlayer if node.has_meta("animation_player") else null
	if player:
		player.seek(fmod(time_ms / 1000.0, player.get_animation("Fly").length), true)

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
	# Desktop bundles supply the data/ directory outside the read-only Godot pack.
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--data-root="):
			var directory = argument.trim_prefix("--data-root=")
			if not directory.is_absolute_path():
				push_error("--data-root must be an absolute data directory")
				set_process(false)
				get_tree().quit(2)
				return
			data_root = directory.path_join("scenarios/v1").simplify_path()
	for required in ["scene.json", "../../site_layout.json", "../../terrain/korea_site.json", "../../terrain/korea_context.json", "cases/case_001/world.json", "cases/case_001/public.json"]:
		if not FileAccess.file_exists(data_root.path_join(required)):
			push_error("Missing simulation data: " + data_root.path_join(required))
			set_process(false)
			get_tree().quit(2)
			return
	site_layout = read_json(data_root.path_join("../../site_layout.json"))
	camera_target = vector(site_layout.camera.target)
	desktop_mode = "--desktop" in OS.get_cmdline_user_args()
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
	geographic_context = read_json(data_root.path_join("../../terrain/korea_context.json"))
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
		camera.far = 60000
	else:
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 5200
		camera.position = vector(site_layout.camera.overview)
		camera.far = 60000
	add_child(camera)
	camera.look_at(camera_target)
	for placement in read_json(data_root.path_join("scene.json"))["environment"]:
		var instance = asset_instance(placement["asset_id"])
		instance.position = vector(placement["position"])
		instance.scale *= vector(placement.get("scale", [1, 1, 1]))
		add_child(instance)
		if placement.has("group"):
			facility_nodes[str(placement.id)] = instance
		if placement.get("ground_to_terrain", false):
			instance.name = placement.id
			field_installations[placement.id] = {"node": instance, "position": vector(placement.position)}
		if placement["asset_id"] == "ground_tile":
			terrain = instance
	add_child(Site.make(site_layout, materials))
	exercise_units = ExerciseUnits.new()
	exercise_units.name = "ExerciseUnits"
	exercise_units.materials = materials
	add_child(exercise_units)
	ground_field_installations()
	if realistic:
		add_realistic_details()
	build_ui()
	load_case("case_001")
	if monitor_mode:
		show_overview()
		start_monitor()
	if desktop_mode:
		start_desktop_controls()
	if "--capture" in OS.get_cmdline_user_args():
		playing = false
		elapsed_ms = minf(435000, float(world_data.duration_ms) * 0.65)
		var captured_airframe = ""
		for argument in OS.get_cmdline_user_args():
			if argument.begins_with("--capture-airframe="):
				captured_airframe = argument.get_slice("=", 1)
		if not captured_airframe.is_empty():
			for index in objects.size():
				if objects[index].node.get_meta("airframe_id") == captured_airframe:
					select_drone(index)
					break
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
		if not captured_airframe.is_empty() and captured_airframe in display_profiles.airframes:
			filename = "drone-follow-%s.png" % captured_airframe
		var capture_root = "res://../artifacts/" if OS.has_feature("editor") else "user://captures/"
		var output = ProjectSettings.globalize_path(capture_root + filename)
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
	credit.text = "TRAINING SCENE / 훈련 장면 · POLY HAVEN · CESIUM · DRONE: ED MACKEY / AGI, CC BY 4.0 · DEM: MAPZEN / USGS\n© OpenStreetMap contributors · © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium"
	credit.add_theme_font_size_override("font_size", 12)
	credit.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.8))
	credit.add_theme_constant_override("shadow_offset_x", 1)
	credit.add_theme_constant_override("shadow_offset_y", 1)
	var layer = CanvasLayer.new()
	layer.add_child(credit)
	add_child(layer)
	credit.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	credit.offset_left = 26
	credit.offset_top = -50
	credit.offset_right = 1300
	credit.offset_bottom = -12

func build_ui() -> void:
	var layer = CanvasLayer.new()
	add_child(layer)
	var panel = PanelContainer.new()
	ui_panel = panel
	panel.theme = SimulationUITheme.make()
	panel.position = Vector2(30, 26)
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.025, 0.045, 0.06, 0.94)
	style.content_margin_left = 22
	style.content_margin_right = 22
	style.content_margin_top = 18
	style.content_margin_bottom = 18
	panel.add_theme_stylebox_override("panel", style)
	layer.add_child(panel)
	var contents = VBoxContainer.new()
	contents.add_theme_constant_override("separation", 12)
	panel.add_child(contents)
	drone_overlay = DroneOverlay.new()
	drone_overlay.camera = camera
	drone_overlay.objects = objects
	layer.add_child(drone_overlay)
	layer.move_child(drone_overlay, 0)
	var header = HBoxContainer.new()
	header.add_theme_constant_override("separation", 18)
	contents.add_child(header)
	ui_title = Label.new()
	ui_title.text = "LOW SKY / 3D VIEW"
	ui_title.add_theme_font_size_override("font_size", 36)
	ui_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(ui_title)
	ui_toggle = Button.new()
	ui_toggle.text = "−"
	ui_toggle.tooltip_text = "Collapse controls / 패널 접기"
	ui_toggle.custom_minimum_size = Vector2(40, 38)
	ui_toggle.pressed.connect(toggle_ui_panel)
	header.add_child(ui_toggle)
	ui_scroll = ScrollContainer.new()
	ui_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	ui_scroll.follow_focus = true
	contents.add_child(ui_scroll)
	var column = VBoxContainer.new()
	ui_body = column
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 12)
	ui_scroll.add_child(column)
	column.minimum_size_changed.connect(resize_ui_panel)
	get_viewport().size_changed.connect(resize_ui_panel)
	if desktop_mode:
		build_desktop_controls(column)
	var subtitle = Label.new()
	subtitle.text = "AUTHOR VIEW / 전체 장면\nFull scene context" if realistic else "ASSET STUDY / AUTHOR VIEW\nBuilding samples + procedural placeholders"
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
	follow_button.text = "Follow selected drone  [F]"
	follow_button.pressed.connect(toggle_follow)
	column.add_child(follow_button)
	var drone_selection = HBoxContainer.new()
	column.add_child(drone_selection)
	previous_drone_button = Button.new()
	previous_drone_button.text = "Previous drone  ["
	previous_drone_button.pressed.connect(func(): select_drone(-1))
	drone_selection.add_child(previous_drone_button)
	next_drone_button = Button.new()
	next_drone_button.text = "Next drone  ]"
	next_drone_button.pressed.connect(func(): select_drone(1))
	drone_selection.add_child(next_drone_button)
	selected_drone_label = Label.new()
	selected_drone_label.add_theme_font_size_override("font_size", 21)
	selected_drone_label.modulate = Color("edb0fb")
	column.add_child(selected_drone_label)
	update_follow_controls()
	var aids = CheckButton.new()
	aids.text = "Show all drones (author view)"
	aids.button_pressed = false
	aids.toggled.connect(set_drone_positions)
	column.add_child(aids)
	time_label = Label.new()
	column.add_child(time_label)
	status_label = Label.new()
	status_label.add_theme_font_size_override("font_size", 24)
	column.add_child(status_label)
	var hint = Label.new()
	hint.text = "Left / Middle drag: pan\nRight / Shift+Left drag: orbit\nWheel: zoom   C: view   H: home\n1 / 2 / 3: branch   R: restart\n[ / ]: previous / next drone   F: follow / overview\nSynthetic observations. No LLM connected."
	if monitor_mode:
		hint.text = "Left / Middle: pan   Right: orbit\nWheel: zoom   C: view   H: home\nReplay control: %s\nLabels: received detections / author view\n[ / ]: previous / next drone   F: follow / overview\nCamera selection: author view" % monitor_base_url
	hint.modulate = Color("91b6b8")
	if realistic:
		hint.text += "\nIllustrative altitude / 표시용 고도\nBeyond local DEM: schematic space"
	column.add_child(hint)
	for label in column.find_children("*", "Label", true, false):
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	resize_ui_panel.call_deferred()

func resize_ui_panel() -> void:
	if not is_instance_valid(ui_scroll):
		return
	var viewport_size = get_viewport().get_visible_rect().size
	ui_panel.custom_minimum_size.x = minf(580, viewport_size.x - 60)
	ui_body.custom_minimum_size.x = ui_panel.custom_minimum_size.x - 64
	var available = viewport_size.y - ui_panel.position.y - 72 - 98
	ui_scroll.custom_minimum_size.y = minf(ui_body.get_combined_minimum_size().y, maxf(120, available)) if ui_body.visible else 0.0
	ui_panel.reset_size.call_deferred()

func toggle_ui_panel() -> void:
	ui_body.visible = not ui_body.visible
	ui_scroll.visible = ui_body.visible
	ui_title.text = "LOW SKY / 3D VIEW" if ui_body.visible else "LOW SKY"
	ui_toggle.text = "−" if ui_body.visible else "+"
	ui_toggle.tooltip_text = "Collapse controls / 패널 접기" if ui_body.visible else "Expand controls / 패널 펼치기"
	# PanelContainer otherwise retains its previous rect after minimum size shrinks.
	resize_ui_panel()

func terrain_caption() -> String:
	if geographic:
		return "Terrain: Gyeonggi DEM  [T]"
	return "Terrain: Plains  [T]" if plains_test else "Terrain: Hills  [T]"

func display_position(authored: Vector3) -> Vector3:
	# Uniform illustrative lift, not terrain-following or flight planning. Keep
	# authored XYZ, received evidence, and timing untouched. Labels inherit the
	# marker node transform once; facilities and parked aircraft never call this.
	if realistic and geographic:
		return authored + Vector3(0, float(terrain_data.get("display_airspace_offset_m", 0)), 0)
	return authored

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
	if is_instance_valid(exercise_units):
		exercise_units.reground(terrain_surface_height)
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
	visual_cast_signature = ""
	clear_mission_vignettes()
	simulation_missions.clear()
	monitor_exercise.clear()
	monitor_tactics.clear()
	tactics_targets.clear()
	tactics_effector_labels.clear()
	if is_instance_valid(exercise_units):
		exercise_units.sync([], terrain_surface_height)
	update_exercise_marker()
	stop_follow()
	selected_drone_index = 0
	detected_ids.clear()
	for item in objects:
		item["node"].queue_free()
	objects.clear()
	case_id = id
	world_data = read_json(data_root.path_join("cases/%s/world.json" % id))
	public_data = read_json(data_root.path_join("cases/%s/public.json" % id))
	for item in world_data["objects"]:
		var instance = asset_instance(item["visual"]["asset_id"], item["visual"].get("size_profile", ""), item["visual"].get("airframe_id", ""))
		instance.position = display_position(vector(item["keyframes"][0]["position"]))
		add_child(instance)
		var label = Label3D.new()
		label.text = item["object_id"]
		label.visible = false
		label.position.y = maxf(0.7, float(instance.get_meta("horizontal_span_m")) * 0.45)
		label.font_size = 40
		label.pixel_size = 0.015 if realistic else 0.03
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		instance.add_child(label)
		objects.append({"object_id": item.object_id, "node": instance, "label": label, "sim": false, "keyframes": item["keyframes"]})
	elapsed_ms = 0
	update_drone_labels()
	update_follow_controls()

func apply_visual_cast(cast: Dictionary) -> void:
	var signature = str(cast.get("signature", "fixture"))
	if signature == visual_cast_signature:
		return
	var assigned: Dictionary = {}
	for entry in cast.get("objects", []):
		if str(entry.airframe_id) in display_profiles.airframes:
			assigned[str(entry.object_id)] = str(entry.airframe_id)
	for index in objects.size():
		var item: Dictionary = objects[index]
		var original: Dictionary = world_data.objects[index].visual
		var airframe_id = str(assigned.get(item.object_id, original.get("airframe_id", display_profiles.default_airframe)))
		if item.node.get_meta("airframe_id") == airframe_id:
			continue
		var replacement = drone_instance(airframe_id, "" if assigned.has(item.object_id) else original.get("size_profile", ""))
		replacement.transform = item.node.transform
		add_child(replacement)
		item.label.reparent(replacement, false)
		item.label.position.y = maxf(0.7, float(replacement.get_meta("horizontal_span_m")) * 0.45)
		item.node.queue_free()
		item.node = replacement
	visual_cast_signature = signature
	update_follow_controls()

func set_drone_positions(enabled: bool) -> void:
	show_drone_positions = enabled
	update_drone_labels()

func update_drone_labels() -> void:
	for item in objects:
		# Physical models belong to the simulation; only labels use detection visibility.
		item.node.visible = true
		var detected = detected_ids.has(item.object_id) and (not monitor_mode or monitor_connected)
		item.sim = show_drone_positions
		item.label.visible = detected or show_drone_positions
		item.label.text = ("AUTHOR " if show_drone_positions else "DETECTED ") + item.object_id
		item.note = ""
		if detected and not show_drone_positions and monitor_mode and monitor_connected:
			var advice = tactics_label_lines(str(item.object_id))
			item.label.text += advice
			item.note = advice.strip_edges().replace("\n", " · ")
		item.label.modulate = Color("edb0fb") if show_drone_positions else Color("78e4d2")
		item.label.outline_modulate.a = 1.0
		# The screen callout handles the selected drone at close range.
		if follow_drone and item == objects[selected_drone_index]:
			item.label.modulate.a = 0.0
			item.label.outline_modulate.a = 0.0

func index_tactics() -> void:
	# Index once per received state so label updates stay linear in the track count.
	tactics_targets.clear()
	tactics_effector_labels.clear()
	for target in monitor_tactics.get("targets", []):
		if target is Dictionary and target.has("object_id"):
			tactics_targets[str(target.object_id)] = target
	for effector in monitor_tactics.get("effectors", []):
		if effector is Dictionary and effector.has("id") and effector.get("label") is Dictionary:
			tactics_effector_labels[str(effector.id)] = str(effector.label.get("en", effector.id))

func tactics_label_lines(object_id: String) -> String:
	# Rule-based training advice from the shared state; never altered by the scene.
	var target = tactics_targets.get(object_id)
	if target == null:
		return ""
	var lines = ""
	var identification = target.get("identification", {})
	if identification is Dictionary and identification.has("lean"):
		lines += "\n" + str(identification.lean).replace("_", " ").to_upper()
		var profile = str(identification.get("profile", "unclassified"))
		if profile != "unclassified":
			lines += " · " + profile.replace("_", " ").to_upper()
	var response = target.get("response", {})
	var allocation = response.get("allocation") if response is Dictionary else null
	if allocation is Dictionary:
		var effector_id = str(allocation.get("effector_id", ""))
		lines += "\nALLOCATED: %s (training record)" % tactics_effector_labels.get(effector_id, effector_id)
	return lines

func standalone_detections() -> Dictionary:
	# Only received, fresh observations from online sources grant label visibility.
	var health: Dictionary = {}
	var records: Dictionary = {}
	var result: Dictionary = {}
	var ttl = float(public_data.get("freshness_ms", 45000))
	for event in public_data.get("source_health", []):
		if event.available_at_ms > elapsed_ms or event.observed_at_ms > elapsed_ms:
			continue
		var previous: Dictionary = health.get(event.source_id, {})
		if previous.is_empty() or event.observed_at_ms > previous.observed_at_ms or (event.observed_at_ms == previous.observed_at_ms and event.available_at_ms >= previous.available_at_ms):
			health[event.source_id] = event
	for event in public_data.get("observations", []):
		if event.get("detected", true) == false or event.available_at_ms > elapsed_ms or event.observed_at_ms > elapsed_ms:
			continue
		var key = event.object_id + ":" + event.source_id
		var previous: Dictionary = records.get(key, {})
		if previous.is_empty() or event.observed_at_ms > previous.observed_at_ms or (event.observed_at_ms == previous.observed_at_ms and event.available_at_ms >= previous.available_at_ms):
			records[key] = event
	for event in records.values():
		var source: Dictionary = health.get(event.source_id, {})
		if not source.is_empty() and source.status == "online" and elapsed_ms - source.observed_at_ms <= ttl and elapsed_ms - event.observed_at_ms <= ttl:
			result[event.object_id] = true
	return result

func _process(delta: float) -> void:
	camera.near = clampf(camera.position.distance_to(camera_target) * 0.02, 0.1, 50.0)
	if monitor_mode:
		var age = Time.get_ticks_msec() - monitor_received_at
		monitor_connected = monitor_connected and age <= 1500
		if monitor_connected:
			elapsed_ms = minf(monitor_clock + (minf(age, 500) * monitor_speed if monitor_playing else 0.0), float(world_data.duration_ms))
	elif playing:
		elapsed_ms = minf(elapsed_ms + delta * 1000, float(world_data.duration_ms))
	if not monitor_mode:
		detected_ids = standalone_detections()
	update_drone_labels()
	for item in objects:
		var frames = item["keyframes"]
		var object_time = exercise_time(str(item.object_id), elapsed_ms)
		var index = 0
		while index < frames.size() - 2 and object_time >= float(frames[index + 1].at_ms):
			index += 1
		var interval = float(frames[index + 1].at_ms) - float(frames[index].at_ms)
		var ratio = clampf((object_time - float(frames[index].at_ms)) / interval, 0, 1)
		item["node"].position = display_position(vector(frames[index]["position"]).lerp(vector(frames[index + 1]["position"]), ratio))
		pose_drone(item.node, vector(frames[index + 1].position) - vector(frames[index].position), object_time)
	update_mission_vignettes()
	if follow_drone:
		update_follow_camera()
	if time_label:
		time_label.text = "%s  |  %03d / %03d s" % [case_id, elapsed_ms / 1000, int(world_data.duration_ms) / 1000]
		time_label.text += "  |  Objects %d · Detected labels %d" % [objects.size(), detected_ids.size()]
		if monitor_mode and monitor_test_run.get("mode") == "seeded":
			time_label.text += "  |  Seed %s" % str(monitor_test_run.get("seed"))
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
	update_follow_controls()

func update_follow_controls() -> void:
	var empty = objects.is_empty()
	selected_drone_index = 0 if empty else clampi(selected_drone_index, 0, objects.size() - 1)
	if drone_overlay:
		drone_overlay.followed_object_id = "" if empty or not follow_drone else str(objects[selected_drone_index].object_id)
	for index in objects.size():
		# The screen overlay supplies readable text in the close camera view.
		# Reduce only its duplicate world label; detection visibility stays intact.
		objects[index].label.pixel_size = (0.015 if realistic else 0.03) * (0.1 if follow_drone and index == selected_drone_index else 1.0)
	if follow_button:
		follow_button.disabled = empty
		follow_button.text = "Return to overview  [F]" if follow_drone else "Follow selected drone  [F]"
	if previous_drone_button:
		previous_drone_button.disabled = empty
	if next_drone_button:
		next_drone_button.disabled = empty
	if selected_drone_label:
		# This is author-camera context, never a received detection or world label.
		selected_drone_label.text = "CAMERA: No drones" if empty else "CAMERA: %s  (%d / %d)\n%s · %s m display span" % [objects[selected_drone_index].object_id, selected_drone_index + 1, objects.size(), display_profiles.airframes[objects[selected_drone_index].node.get_meta("airframe_id")].label, objects[selected_drone_index].node.get_meta("horizontal_span_m")]

func select_drone(offset: int) -> void:
	if objects.is_empty():
		stop_follow()
		return
	selected_drone_index = posmod(selected_drone_index + offset, objects.size())
	follow_drone = true
	update_follow_controls()
	update_follow_camera()

func toggle_follow() -> void:
	if follow_drone:
		show_overview()
	elif not objects.is_empty():
		follow_drone = true
		update_follow_controls()
		update_follow_camera()

func update_follow_camera() -> void:
	if objects.is_empty():
		return
	camera_target = objects[selected_drone_index].node.position
	var span = float(objects[selected_drone_index].node.get_meta("horizontal_span_m", 0.6))
	camera.position = camera_target + Vector3(1.5, 0.9, 2.2) * span
	camera.size = span * 2.8
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
	target.z = clampf(target.z, -25000, 6000)
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
	if desktop_mode and event is InputEventKey and event.pressed and not event.echo and event.keycode in [KEY_F6, KEY_F11]:
		desktop_command("show_monitor" if event.keycode == KEY_F6 else "toggle_3d_fullscreen")
		get_viewport().set_input_as_handled()
		return
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
			KEY_BRACKETLEFT: select_drone(-1)
			KEY_BRACKETRIGHT: select_drone(1)
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
		monitor_request.request(monitor_base_url + "/api/state?show_positions=1")

func receive_monitor_clock(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		monitor_connected = false
		detected_ids.clear()
		update_drone_labels()
		return
	var state = JSON.parse_string(body.get_string_from_utf8())
	if not state is Dictionary or not state.has_all(["case_id", "at_ms", "playing", "speed", "tracks"]) or not state.tracks is Array:
		monitor_connected = false
		detected_ids.clear()
		update_drone_labels()
		return
	var next_case = str(state.case_id)
	if not next_case.begins_with("case_") or not next_case.substr(5).is_valid_int():
		monitor_connected = false
		detected_ids.clear()
		update_drone_labels()
		return
	if next_case != case_id:
		if not FileAccess.file_exists(data_root.path_join("cases/%s/world.json" % next_case)):
			monitor_connected = false
			detected_ids.clear()
			update_drone_labels()
			return
		load_case(next_case)
	apply_visual_cast(state.get("simulation_visuals", {}))
	detected_ids.clear()
	for track in state.tracks:
		if track is Dictionary and track.has("object_id") and not track.get("last_known", true):
			detected_ids[str(track.object_id)] = true
	monitor_clock = float(state.at_ms)
	monitor_test_run = state.get("test_run", {})
	monitor_exercise = state.get("exercise", {})
	exercise_units.sync(monitor_exercise.get("units", []), terrain_surface_height, monitor_exercise.get("unit_kinds", []))
	var tactics = state.get("tactics", {})
	monitor_tactics = tactics if tactics is Dictionary else {}
	index_tactics()
	# Physical author view only; labels still use received tracks above.
	simulation_missions = state.get("simulation_missions", monitor_exercise.get("missions", []))
	update_exercise_marker()
	monitor_speed = float(state.speed)
	monitor_playing = bool(state.playing)
	monitor_received_at = Time.get_ticks_msec()
	monitor_connected = true
	elapsed_ms = monitor_clock
	update_drone_labels()

func exercise_time(object_id: String, at_ms: float) -> float:
	var selection = monitor_exercise.get("selection")
	if not monitor_mode or selection == null or str(selection.object_id) != object_id or at_ms < float(selection.effective_at_ms):
		return at_ms
	if selection.branch_id == "hold":
		return float(selection.effective_at_ms)
	if selection.branch_id == "withdraw":
		return maxf(0.0, 2.0 * float(selection.effective_at_ms) - at_ms)
	return at_ms

func update_exercise_marker() -> void:
	var selection = monitor_exercise.get("selection")
	if selection == null:
		if is_instance_valid(exercise_marker):
			exercise_marker.visible = false
		return
	if not is_instance_valid(exercise_marker):
		exercise_marker = Label3D.new()
		exercise_marker.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		exercise_marker.font_size = 48
		exercise_marker.pixel_size = 0.25
		add_child(exercise_marker)
	for asset in monitor_exercise.get("assets", []):
		if asset.id == selection.asset_id:
			exercise_marker.position = vector(asset.position) + Vector3(0, 45, 0)
			exercise_marker.text = "%s · %s\n%s" % [asset.label.en, str(asset.status).to_upper(), str(selection.status).to_upper()]
			exercise_marker.modulate = Color(1.0, 0.7, 0.3) if asset.status != "available" else Color(0.5, 1.0, 0.7)
			exercise_marker.visible = true
			return


func clear_mission_vignettes() -> void:
	for facility in facility_nodes.values():
		set_facility_charred(facility, false)
	for node in mission_nodes.values():
		node.queue_free()
	mission_nodes.clear()

func set_facility_charred(facility: Node3D, charred: bool) -> void:
	if bool(facility.get_meta("charred", false)) == charred:
		return
	facility.set_meta("charred", charred)
	for mesh in facility.find_children("*", "MeshInstance3D", true, false):
		if charred:
			mesh.set_meta("original_material", mesh.material_override)
			mesh.material_override = solid_material(Color("292725"), 0.05, 1.0)
		else:
			mesh.material_override = mesh.get_meta("original_material", null)

func make_result_effects(root: Node3D) -> void:
	var effects = Node3D.new()
	effects.name = "Damage"
	root.add_child(effects)
	var shader_base = """shader_type spatial;
render_mode unshaded, cull_disabled, blend_mix, depth_draw_never;
uniform float clock = 0.0;
uniform float opacity = 1.0;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p), f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0)), f.x), f.y);
}
float turbulence(vec2 p) { return noise(p) * 0.57 + noise(p * 2.1) * 0.28 + noise(p * 4.3) * 0.15; }
"""
	var flame_shader = Shader.new()
	flame_shader.code = shader_base + """
void fragment() {
	float height = 1.0 - UV.y;
	float n = turbulence(UV * vec2(5.0, 4.0) + vec2(clock * 0.21, clock * 2.1));
	float sway = sin(height * 5.0 - clock * 3.4) * height * 0.22 + (n - 0.5) * 0.3;
	float width = pow(1.0 - height, 0.85) * 0.8 + 0.015;
	float edge = abs(UV.x * 2.0 - 1.0 - sway);
	float shape = (1.0 - smoothstep(width * 0.22, width, edge)) * smoothstep(0.0, 0.14, height);
	float heat = clamp((1.0 - height) * 0.8 + (1.0 - edge / max(width, 0.01)) * 0.4, 0.0, 1.0);
	ALBEDO = mix(vec3(0.95, 0.13, 0.01), vec3(1.0, 0.83, 0.21), heat);
	EMISSION = ALBEDO * 0.65;
	ALPHA = shape * smoothstep(0.16, 0.58, n + (1.0 - height) * 0.23) * opacity;
}
"""
	var smoke_shader = Shader.new()
	smoke_shader.code = shader_base + """
void fragment() {
	vec2 p = UV - vec2(0.5);
	float n = turbulence(UV * 5.0 + vec2(clock * 0.08, -clock * 0.19));
	float edge = length(p * vec2(1.0, 0.92)) + (n - 0.5) * 0.22;
	float feather = 1.0 - smoothstep(0.08, 0.49, edge);
	ALBEDO = mix(vec3(0.09, 0.095, 0.105), vec3(0.28, 0.29, 0.30), n);
	ALPHA = feather * feather * (0.4 + n * 0.6) * opacity;
}
"""
	for index in range(25):
		var piece = MeshInstance3D.new()
		var quad = QuadMesh.new()
		quad.size = Vector2(2, 2)
		piece.mesh = quad
		var material = ShaderMaterial.new()
		material.shader = flame_shader if index < 9 else smoke_shader
		piece.material_override = material
		piece.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		piece.name = ("Flame" if index < 9 else "Smoke") + str(index)
		effects.add_child(piece)
	var debris = Node3D.new()
	debris.name = "Debris"
	effects.add_child(debris)
	for index in range(16):
		var angle = index * 2.39996
		var radius = 17.0 + float(index % 4) * 5.0
		var piece = Detailed.box(debris, Vector3(3.0 + index % 3, 1.8, 4.0), Vector3(cos(angle) * radius, -33.5, sin(angle) * radius), solid_material(Color("39332d")))
		piece.rotation = Vector3(index * 0.13, angle, index * 0.27)
	var flash = MeshInstance3D.new()
	flash.name = "Flash"
	var sphere = SphereMesh.new()
	sphere.radius = 1
	sphere.height = 2
	flash.mesh = sphere
	var glow = solid_material(Color("ffe6a6"))
	glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	flash.material_override = glow
	root.add_child(flash)

func pose_result_effects(node: Node3D, anchor: Vector3, phase: String, result_at_ms: float) -> void:
	# Every pose comes from the shared clock: seek/reset never leave particles behind.
	var damage: Node3D = node.get_node("Damage")
	var flash: MeshInstance3D = node.get_node("Flash")
	damage.visible = phase == "complete"
	var age = maxf(0.0, elapsed_ms - result_at_ms) / 1000.0
	flash.visible = phase == "complete" and age < 1.2
	damage.position = anchor
	flash.position = anchor
	flash.scale = Vector3.ONE * (4.0 + minf(age, 1.2) * 25.0)
	flash.material_override.albedo_color.a = maxf(0, 1.0 - age / 1.2)
	if not damage.visible:
		return
	for index in range(25):
		var piece: MeshInstance3D = damage.get_child(index)
		var angle = index * 2.39996
		piece.quaternion = camera.quaternion
		piece.material_override.set_shader_parameter("clock", age + index * 0.31)
		if index < 9:
			var flicker = 0.7 + 0.3 * sin(age * 7.0 + index * 1.7)
			piece.position = Vector3(cos(angle) * 9.0, -18.0 + flicker * 7.0, sin(angle) * 9.0)
			piece.scale = Vector3(7.0, 12.0 + index % 3 * 3.0, 1.0) * flicker
		else:
			var rise = fmod(age * 0.16 + (index - 9) / 16.0, 1.0)
			piece.position = Vector3(cos(angle) * (8 + rise * 16) + rise * 15, -8 + rise * 100, sin(angle) * (8 + rise * 16))
			piece.scale = Vector3(1.0, 1.15, 1.0) * (15 + rise * 30)
			piece.material_override.set_shader_parameter("opacity", (1.0 - rise) * 0.9)

func make_mission_vignette() -> Node3D:
	var node = Node3D.new()
	var payload = MeshInstance3D.new()
	payload.name = "Payload"
	var cube = BoxMesh.new()
	cube.size = Vector3.ONE * 3.0
	payload.mesh = cube
	payload.material_override = solid_material(Color("ffc778"), 0.1)
	node.add_child(payload)
	make_result_effects(node)
	var label = Label3D.new()
	label.name = "Label"
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.font_size = 42
	label.pixel_size = 0.12
	node.add_child(label)
	add_child(node)
	return node

func update_mission_vignettes() -> void:
	# Fixed scene illustration only: no physics, targeting or effectiveness model.
	var present: Dictionary = {}
	var charred_facilities: Dictionary = {}
	for mission in simulation_missions:
		var id = str(mission.id)
		present[id] = true
		if not mission_nodes.has(id):
			mission_nodes[id] = make_mission_vignette()
		var node: Node3D = mission_nodes[id]
		var anchor = Vector3.ZERO
		var found = false
		for asset in monitor_exercise.get("assets", []):
			if asset.id == mission.asset_id:
				anchor = vector(asset.position) + Vector3(0, 35, 0)
				found = true
		var phase = str(mission.phase)
		node.set_meta("phase", phase)
		node.visible = found and phase != "approach"
		var payload: MeshInstance3D = node.get_node("Payload")
		var label: Label3D = node.get_node("Label")
		payload.visible = false
		label.visible = (detected_ids.has(str(mission.object_id)) and (not monitor_mode or monitor_connected)) or show_drone_positions
		label.position = anchor + Vector3(0, 35, 0)
		label.text = {"finale": "DESCENT / 하강", "complete": "FACILITY DAMAGE / 시설 피해", "partial": "RESTRICTED / 제한 운영", "prevented": "FACILITY CLEAR / 시설 정상"}.get(phase, phase.to_upper())
		pose_result_effects(node, anchor, phase if found else "approach", float(mission.get("result_at_ms", mission.phase_start_ms) if mission.get("result_at_ms") != null else mission.phase_start_ms))
		if found and phase == "complete":
			charred_facilities[str(mission.asset_id)] = true
		if not node.visible:
			continue
		var progress = clampf((elapsed_ms - float(mission.phase_start_ms)) / maxf(1, float(mission.phase_end_ms) - float(mission.phase_start_ms)), 0, 1)
		var top = display_position(anchor + Vector3(0, 100, 0))
		var is_drop = mission.kind == "drop_vignette"
		var actor = objects.filter(func(item): return item.object_id == mission.object_id)
		if phase == "finale":
			if not actor.is_empty():
				actor[0].node.position = top + Vector3(progress * 160, progress * 35, 0) if is_drop else top.lerp(anchor, progress)
			payload.visible = is_drop
			payload.position = top.lerp(anchor, progress)
		elif phase == "complete":
			if not actor.is_empty():
				actor[0].node.position = top + Vector3(160 + minf(maxf(elapsed_ms - float(mission.phase_start_ms), 0) / 1000, 30) * 8, 35, 0) if is_drop else anchor
		var color = Color("79e8b0") if phase == "prevented" else (Color("ffc778") if phase == "partial" else Color("f09372"))
		label.modulate = color
	for id in facility_nodes:
		set_facility_charred(facility_nodes[id], charred_facilities.has(id))
	for id in mission_nodes.keys():
		if not present.has(id):
			mission_nodes[id].queue_free()
			mission_nodes.erase(id)


func build_desktop_controls(column: VBoxContainer) -> void:
	var row = HBoxContainer.new()
	column.add_child(row)
	desktop_monitor_button = Button.new()
	desktop_monitor_button.text = "Monitoring [F6]"
	desktop_monitor_button.tooltip_text = "Return to monitoring [F6]"
	desktop_monitor_button.add_theme_font_size_override("font_size", 20)
	desktop_monitor_button.disabled = true
	desktop_monitor_button.pressed.connect(func(): desktop_command("show_monitor"))
	row.add_child(desktop_monitor_button)
	desktop_fullscreen_button = Button.new()
	desktop_fullscreen_button.text = "Fullscreen [F11]"
	desktop_fullscreen_button.tooltip_text = "Toggle full screen [F11]"
	desktop_fullscreen_button.add_theme_font_size_override("font_size", 20)
	desktop_fullscreen_button.disabled = true
	desktop_fullscreen_button.pressed.connect(func(): desktop_command("toggle_3d_fullscreen"))
	row.add_child(desktop_fullscreen_button)
	desktop_status = Label.new()
	desktop_status.add_theme_font_size_override("font_size", 18)
	desktop_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desktop_status.custom_minimum_size.x = 300
	desktop_status.text = "Connecting window controls… / 창 제어 연결 중"
	column.add_child(desktop_status)

func start_desktop_controls() -> void:
	desktop_poll_request = HTTPRequest.new()
	desktop_poll_request.timeout = 1.0
	desktop_poll_request.request_completed.connect(receive_desktop_state)
	add_child(desktop_poll_request)
	desktop_command_request = HTTPRequest.new()
	desktop_command_request.timeout = 2.0
	desktop_command_request.request_completed.connect(receive_desktop_state)
	add_child(desktop_command_request)
	var timer = Timer.new()
	timer.wait_time = 0.4
	timer.timeout.connect(poll_desktop_state)
	add_child(timer)
	timer.start()
	poll_desktop_state()

func poll_desktop_state() -> void:
	if desktop_mode and desktop_poll_request.get_http_client_status() == HTTPClient.STATUS_DISCONNECTED:
		if desktop_poll_request.request(monitor_base_url + "/api/desktop") != OK:
			set_desktop_error("Window controls unavailable / 창 제어 연결 실패")

func desktop_command(action: String) -> void:
	if not desktop_mode or not is_instance_valid(desktop_command_request):
		return
	if not desktop_state.get("available", false) or desktop_state.get("pending", false) or desktop_command_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		return
	var error = desktop_command_request.request(monitor_base_url + "/api/desktop", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify({"action":action}))
	if error != OK:
		set_desktop_error("Window command failed / 창 제어 요청 실패")

func set_desktop_error(message: String) -> void:
	if is_instance_valid(desktop_status):
		desktop_status.text = message.left(180)
		desktop_status.modulate = Color("ffc778")

func receive_desktop_state(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS:
		set_desktop_error("Window controls disconnected; retrying / 창 제어 재연결 중")
		return
	var state = JSON.parse_string(body.get_string_from_utf8())
	if response_code not in [200, 202]:
		set_desktop_error("Window command rejected (%s) / 창 제어 요청 거절" % response_code)
		return
	if not state is Dictionary or not state.has_all(["available", "view", "fullscreen", "three_d_open", "pending", "error", "revision"]):
		set_desktop_error("Invalid window state / 창 제어 응답 오류")
		return
	apply_desktop_state(state)

func apply_desktop_state(state: Dictionary) -> Dictionary:
	# This transport never reads or writes the simulation clock. Return the intended
	# native actions so headless verification does not need OS focus or fullscreen.
	if not desktop_mode or int(state.revision) < desktop_revision:
		return {}
	desktop_state = state.duplicate(true)
	if is_instance_valid(desktop_status):
		desktop_monitor_button.disabled = not state.available or state.pending
		desktop_fullscreen_button.disabled = not state.available or state.pending
		desktop_status.modulate = Color("91b6b8")
		if not state.available:
			desktop_status.text = "Window controls unavailable / 창 제어 사용 불가"
		elif state.error != null and not str(state.error).is_empty():
			set_desktop_error("Window control: " + str(state.error))
		elif state.pending:
			desktop_status.text = "Switching window… / 창 전환 중"
		else:
			desktop_status.text = "F6 · Monitoring / 모니터링    F11 · Fullscreen / 전체 화면"
	if int(state.revision) == desktop_revision:
		return {}
	desktop_revision = int(state.revision)
	if not state.available or state.pending or (state.error != null and not str(state.error).is_empty()):
		return {}
	var focus_3d = state.view == "3d"
	# Even a background mode change can steal native focus or switch macOS Spaces.
	# Keep the desired fullscreen value in desktop_state until 3D is requested.
	var actions = {"fullscreen": bool(state.fullscreen) if focus_3d else null, "focus": focus_3d}
	if actions.focus and DisplayServer.get_name() != "headless":
		var native_fullscreen = get_window().mode in [Window.MODE_FULLSCREEN, Window.MODE_EXCLUSIVE_FULLSCREEN]
		if actions.fullscreen != native_fullscreen:
			get_window().mode = Window.MODE_FULLSCREEN if actions.fullscreen else Window.MODE_WINDOWED
		get_window().grab_focus()
		DisplayServer.window_move_to_foreground(get_window().get_window_id())
	return actions
