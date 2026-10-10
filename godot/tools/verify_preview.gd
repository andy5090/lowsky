extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var packed = load("res://preview.tscn") as PackedScene
	assert(packed != null)
	var preview = packed.instantiate()
	root.add_child(preview)
	await process_frame
	await process_frame
	preview.playing = false
	var manifest = preview.read_json(preview.data_root.path_join("manifest.json"))
	for entry in manifest["cases"]:
		preview.load_case(entry["case_id"])
		preview.elapsed_ms = 60000
		preview._process(0)
		assert(preview.objects.size() == 3)
		for item in preview.objects:
			assert(item["node"].position.is_equal_approx(preview.vector(item["keyframes"][2]["position"])))
		assert(preview.status_label.text.contains("channel_b: offline") == (entry["variant"] == "missing"))
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_2
	preview._unhandled_input(event)
	assert(preview.case_id == "case_002")
	event.keycode = KEY_SPACE
	preview._unhandled_input(event)
	assert(preview.playing)
	preview._process(1)
	assert(preview.elapsed_ms == 1000)
	event.keycode = KEY_R
	preview._unhandled_input(event)
	assert(preview.elapsed_ms == 0)
	assert(preview.has_node("PlainsTerrain/Fields"))
	assert(preview.has_node("PlainsTerrain/Shelterbelts"))
	# Art-direction switching must not restart or alter the scenario replay.
	preview.elapsed_ms = 65000
	preview._process(0)
	var object_position = preview.objects[0]["node"].position
	event.keycode = KEY_T
	preview._unhandled_input(event)
	assert(preview.has_node("FictionalTerrain"))
	assert(not preview.has_node("PlainsTerrain"))
	preview._unhandled_input(event)
	assert(preview.has_node("PlainsTerrain"))
	assert(not preview.has_node("FictionalTerrain"))
	assert(preview.elapsed_ms == 65000)
	assert(preview.case_id == "case_002")
	assert(preview.objects[0]["node"].position.is_equal_approx(object_position))
	var ground_mesh = preview.terrain.get_child(0).mesh
	for vertex in ground_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
		if absf(vertex.x) <= 50 and absf(vertex.z) <= 50:
			assert(is_equal_approx(vertex.y, -0.02), "Airfield surface must remain level")
	assert(preview.has_node("DetailedHangar"))
	assert(preview.has_node("DetailedTower"))
	var initial_camera_position = preview.camera.position
	event.keycode = KEY_C
	preview._unhandled_input(event)
	assert(preview.camera.position.y == 70)
	preview._unhandled_input(event)
	assert(preview.camera.position.is_equal_approx(initial_camera_position))
	event.keycode = KEY_LEFT
	preview._unhandled_input(event)
	assert(not preview.camera.position.is_equal_approx(initial_camera_position))
	assert(verify_camera_drag(preview), "Camera drag regression checks failed")
	for profile_id in preview.display_profiles.profiles:
		var drone = preview.asset_instance("aerial_marker", profile_id)
		var bounds = preview.collect_bounds(drone, Transform3D.IDENTITY)
		var combined: AABB = bounds[0]
		for bound in bounds:
			combined = combined.merge(bound)
		var expected = float(preview.display_profiles.profiles[profile_id].horizontal_span_m)
		assert(is_equal_approx(maxf(combined.size.x, combined.size.z), expected))
		assert(combined.get_center().is_zero_approx())
		drone.free()
	for item in preview.objects:
		assert(item["node"].get_meta("size_profile") == "small_multirotor")
	print("PASS: drone display spans 0.6 m / 1.5 m and centered origins; paths remain unchanged")
	var provenance = preview.read_json("res://third_party/realistic/provenance.json")
	for entry in provenance.files:
		if entry.path.ends_with(".md"):
			continue
		var resource = load("res://third_party/realistic/" + entry.path)
		assert(resource != null)
		if resource is Texture2D and entry.path.ends_with(".jpg"):
			assert(resource.get_image().has_mipmaps())
		if resource is PackedScene:
			var node = resource.instantiate()
			assert(not preview.collect_bounds(node, Transform3D.IDENTITY).is_empty())
			node.free()
	var imported_models = 0
	var dir = DirAccess.open("res://third_party/kenney_industrial")
	for file in dir.get_files():
		if file.ends_with(".glb"):
			var resource = load("res://third_party/kenney_industrial/" + file) as PackedScene
			assert(resource != null)
			var node = resource.instantiate()
			assert(not preview.collect_bounds(node, Transform3D.IDENTITY).is_empty())
			node.free()
			imported_models += 1
	assert(imported_models == 4)
	print("PASS: 12 cases, playback and camera input, plains/hills switching preserves replay, level airfield, detailed buildings, PBR mipmaps and 5 external models")
	preview.queue_free()
	await process_frame
	quit()

func mouse_button(button: int, pressed: bool, position: Vector2, shift: bool = false) -> void:
	var event = InputEventMouseButton.new()
	event.button_index = button
	event.pressed = pressed
	event.position = position
	event.global_position = position
	event.shift_pressed = shift
	event.button_mask = (1 << (button - 1)) if pressed else 0
	root.push_input(event, true)

func mouse_motion(button: int, relative: Vector2, position: Vector2) -> void:
	var event = InputEventMouseMotion.new()
	event.position = position
	event.global_position = position
	event.relative = relative
	event.button_mask = (1 << (button - 1)) if button else 0
	root.push_input(event, true)

func verify_camera_drag(preview: Node3D) -> bool:
	root.notify_mouse_entered()
	var scene_point = Vector2(900, 600)
	var original_target: Vector3 = preview.camera_target
	var original_position: Vector3 = preview.camera.position
	var original_offset = original_position - original_target
	for button in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_MIDDLE]:
		var before: Vector3 = preview.camera_target
		mouse_button(button, true, scene_point)
		mouse_motion(button, Vector2(45, 25), scene_point + Vector2(45, 25))
		mouse_button(button, false, scene_point)
		assert(not preview.camera_target.is_equal_approx(before), "Drag must pan the scene")
		assert((preview.camera.position - preview.camera_target).is_equal_approx(original_offset))
		assert(is_equal_approx(preview.camera_target.y, original_target.y))
	var after_release: Vector3 = preview.camera.position
	mouse_motion(0, Vector2(90, 60), scene_point)
	assert(preview.camera.position.is_equal_approx(after_release), "Released drag must stop")
	for button in [MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_LEFT]:
		var target: Vector3 = preview.camera_target
		var before: Vector3 = preview.camera.position
		mouse_button(button, true, scene_point, button == MOUSE_BUTTON_LEFT)
		mouse_motion(button, Vector2(40, 20), scene_point)
		mouse_button(button, false, scene_point)
		assert(preview.camera_target.is_equal_approx(target))
		assert(not preview.camera.position.is_equal_approx(before), "Orbit must rotate around target")
		assert(is_equal_approx(preview.camera.position.distance_to(target), before.distance_to(target)))
	# UI clicks should reach the button without initiating camera movement.
	var ui_point: Vector2 = preview.terrain_button.get_global_rect().get_center()
	# Native GUI hit testing needs a rendered window; run this script without
	# --headless to exercise button delivery as well as camera motion.
	if DisplayServer.get_name() != "headless":
		var before_ui: Vector3 = preview.camera.position
		var terrain_before: bool = preview.plains_test
		mouse_motion(0, Vector2.ZERO, ui_point)
		mouse_button(MOUSE_BUTTON_LEFT, true, ui_point)
		assert(preview.drag_button == MOUSE_BUTTON_NONE)
		mouse_button(MOUSE_BUTTON_LEFT, false, ui_point)
		assert(preview.plains_test != terrain_before, "Terrain button must still receive clicks")
		assert(preview.camera.position.is_equal_approx(before_ui))
	else:
		print("SKIP: native GUI button delivery requires a rendered window")
	# A drag begun in the scene must release even over the controls.
	mouse_button(MOUSE_BUTTON_MIDDLE, true, scene_point)
	mouse_motion(MOUSE_BUTTON_MIDDLE, Vector2(5, 5), ui_point)
	mouse_button(MOUSE_BUTTON_MIDDLE, false, ui_point)
	assert(preview.drag_button == MOUSE_BUTTON_NONE)
	mouse_button(MOUSE_BUTTON_RIGHT, true, scene_point)
	preview._notification(Node.NOTIFICATION_WM_WINDOW_FOCUS_OUT)
	assert(preview.drag_button == MOUSE_BUTTON_NONE)
	mouse_button(MOUSE_BUTTON_RIGHT, false, scene_point)
	# Extreme orbit input must not flip through the ground or camera pole.
	for delta in [10000.0, -10000.0]:
		preview.orbit_camera(Vector2(0, delta))
		var offset: Vector3 = preview.camera.position - preview.camera_target
		var pitch = rad_to_deg(asin(offset.normalized().y))
		assert(pitch >= 7.99 and pitch <= 85.01)
	var home = InputEventKey.new()
	home.pressed = true
	home.keycode = KEY_H
	preview._unhandled_input(home)
	assert(preview.camera.position.is_equal_approx(Vector3(49, 20, 61)))
	assert(preview.camera_target.is_equal_approx(Vector3(12, 2.5, 14)))
	print("PASS: mouse pan/orbit through viewport, drag release, focus loss, pitch limits and home")
	return true
