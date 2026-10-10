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
		preview.elapsed_ms = float(preview.world_data.duration_ms)
		preview._process(0)
		assert(preview.objects.size() == preview.world_data.objects.size())
		for item in preview.objects:
			assert(item["node"].position.is_equal_approx(preview.display_position(preview.vector(item["keyframes"][-1]["position"]))))
		assert(preview.objects.size() > 0)
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
	assert(preview.has_node("GeographicTerrain"))
	assert(preview.terrain.get_meta("triangle_count") == 80000)
	var reference = float(preview.terrain_data.reference_elevation_m)
	assert(is_equal_approx(preview.Geographic.elevation(preview.terrain_data, -300, 0, preview.site_layout), -0.02))
	assert(is_equal_approx(preview.Geographic.elevation(preview.terrain_data, -5000, -5000, preview.site_layout), float(preview.terrain_data.heights_m[0][0]) - reference))
	# Beyond the polygon's grading margin and blend, DEM heights are unmodified.
	assert(is_equal_approx(preview.Geographic.elevation(preview.terrain_data, 1100, 1900, preview.site_layout), float(preview.terrain_data.heights_m[138][122]) - reference))
	verify_site_geometry(preview)
	verify_field_grounding(preview)
	# Terrain modes must not restart or alter replay.
	preview.elapsed_ms = 65000
	preview._process(0)
	var object_position = preview.objects[0]["node"].position
	var frames: Array = preview.objects[0].keyframes
	var index = 0
	while index < frames.size() - 2 and preview.elapsed_ms >= float(frames[index + 1].at_ms):
		index += 1
	var ratio = (preview.elapsed_ms - float(frames[index].at_ms)) / (float(frames[index + 1].at_ms) - float(frames[index].at_ms))
	var expected_midpoint = preview.display_position(preview.vector(frames[index].position).lerp(preview.vector(frames[index + 1].position), ratio))
	assert(object_position.is_equal_approx(expected_midpoint), "Position uses authored keyframe intervals plus display-only altitude")
	event.keycode = KEY_T
	preview._unhandled_input(event)
	assert(preview.has_node("PlainsTerrain/Fields"))
	assert(preview.has_node("PlainsTerrain/Shelterbelts"))
	verify_field_grounding(preview)
	preview._unhandled_input(event)
	assert(preview.has_node("FictionalTerrain"))
	verify_field_grounding(preview)
	preview._unhandled_input(event)
	assert(preview.has_node("GeographicTerrain"))
	verify_field_grounding(preview)
	assert(preview.elapsed_ms == 65000)
	assert(preview.case_id == "case_002")
	assert(preview.objects[0]["node"].position.is_equal_approx(object_position))
	var ground_mesh = preview.terrain.get_child(0).mesh
	for vertex in ground_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
		if absf(vertex.x) <= 50 and absf(vertex.z) <= 50:
			assert(is_equal_approx(vertex.y, -0.02), "Airfield surface must remain level")
	assert(preview.has_node("DetailedHangar"))
	assert(preview.has_node("ArchedHangar"))
	assert(preview.has_node("OfficeBuilding"))
	assert(preview.has_node("ServiceBuilding"))
	assert(preview.has_node("pole_phone_1") and preview.has_node("pole_phone_2"))
	assert(preview.has_node("DetailedTower"))
	assert(preview.get_node("SiteInfrastructure/Runway").get_meta("length_m") == 2500)
	assert(preview.get_node("SiteInfrastructure/PerimeterFence").get_meta("vertex_count") == preview.site_layout.perimeter.polygon.size())
	var initial_camera_position = preview.camera.position
	event.keycode = KEY_C
	preview._unhandled_input(event)
	assert(preview.camera.position.y == preview.site_layout.camera.overview[1])
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
		var airframe = preview.display_profiles.airframes[item.node.get_meta("airframe_id")]
		assert(item.node.get_meta("size_profile") == airframe.size_profile)
	print("PASS: calibrated drone display spans and centered origins; paths remain unchanged")
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
	verify_mission_vignettes(preview)
	print("PASS: all manifest cases, playback and camera input, DEM and terrain switching preserve replay, irregular airfield, connected taxiways, detailed buildings and external models")
	preview.queue_free()
	await process_frame
	quit()

func verify_site_geometry(preview: Node3D) -> void:
	var layout: Dictionary = preview.site_layout
	var polygon = PackedVector2Array()
	for corner in layout.perimeter.polygon:
		polygon.append(Vector2(corner[0], corner[1]))
	assert(polygon.size() > 4, "Site boundary must be an irregular polygon")
	for facility in layout.facilities:
		assert(Geometry2D.is_point_in_polygon(Vector2(facility.position[0], facility.position[2]), polygon))
		assert(is_equal_approx(preview.Geographic.elevation(preview.terrain_data, facility.position[0], facility.position[2], layout), -0.02))
		assert(not facility.label.en.is_empty() and not facility.label.ko.is_empty())
		var building = preview.asset_instance(facility.asset_id)
		building.scale = preview.vector(facility.scale)
		building.position = preview.vector(facility.position)
		var bounds = preview.collect_bounds(building, Transform3D.IDENTITY)
		assert(not bounds.is_empty())
		var combined: AABB = bounds[0]
		for bound in bounds:
			combined = combined.merge(bound)
		for x in [combined.position.x, combined.end.x]:
			for z in [combined.position.z, combined.end.z]:
				assert(Geometry2D.is_point_in_polygon(Vector2(x, z), polygon), facility.id + " footprint exceeds boundary")
		if facility.asset_id == "arched_hangar":
			assert(combined.size.x < 70 and combined.size.z < 80 and combined.size.y < 20, "Arched hangars must preserve ordinary building scale")
		building.free()
	assert(layout.display_zones.size() == 5)
	for zone in layout.display_zones:
		assert(preview.has_node("SiteInfrastructure/DisplayZones/" + zone.id))
		var inside = Geometry2D.is_point_in_polygon(Vector2(zone.position[0], zone.position[2]), polygon)
		assert(inside != bool(zone.get("ground_to_terrain", false)))
	for installation in layout.field_installations:
		assert(not Geometry2D.is_point_in_polygon(Vector2(installation.position[0], installation.position[2]), polygon), "Field poles must be outside the fence")
		var node = preview.get_node(installation.id)
		var bounds = preview.collect_bounds(node, Transform3D.IDENTITY)
		var combined: AABB = bounds[0]
		for bound in bounds:
			combined = combined.merge(bound)
		assert(is_equal_approx(combined.size.y, 3.0) and combined.size.x < 1 and combined.size.z < 1, "Phone mount must remain a 3 m ordinary pole")
	# Procedural aliases also work with existing stylized and blockout resources.
	preview.realistic = false
	for external in [true, false]:
		preview.use_external_assets = external
		for asset in ["arched_hangar", "office_building", "service_building", "phone_sensor_pole"]:
			var fallback = preview.asset_instance(asset)
			assert(not preview.collect_bounds(fallback, Transform3D.IDENTITY).is_empty())
			fallback.free()
	preview.realistic = true
	preview.use_external_assets = true
	for apron in layout.aprons:
		for dx in [-1, 1]:
			for dz in [-1, 1]:
				assert(Geometry2D.is_point_in_polygon(Vector2(apron.center[0] + dx * apron.width_m * 0.5, apron.center[2] + dz * apron.length_m * 0.5), polygon))
	var runway: Dictionary = layout.runway
	for dx in [-1, 1]:
		for dz in [-1, 1]:
			assert(Geometry2D.is_point_in_polygon(Vector2(runway.center[0] + dx * runway.width_m * 0.5, runway.center[2] + dz * runway.length_m * 0.5), polygon))
	var parallel: Dictionary = layout.taxiways[0]
	var spine_start = Vector2(parallel.points[0][0], parallel.points[0][1])
	var spine_end = Vector2(parallel.points[1][0], parallel.points[1][1])
	for path in layout.taxiways + layout.roads:
		assert(preview.has_node("SiteInfrastructure/" + path.id))
		for point in path.points:
			assert(Geometry2D.is_point_in_polygon(Vector2(point[0], point[1]), polygon))
	for taxiway in layout.taxiways.slice(1):
		var connected = false
		for point in taxiway.points:
			var position = Vector2(point[0], point[1])
			connected = connected or position.distance_to(Geometry2D.get_closest_point_to_segment(position, spine_start, spine_end)) < 0.01
		assert(connected, "Every taxi connector must meet the parallel taxiway")
	# The removed corner of the old rectangle must no longer be a flat plateau.
	assert(preview.Geographic.grading_distance(600, 1450, layout) > 350)
	assert(preview.Geographic.grading_distance(-300, 0, layout) < 0)
	print("PASS: polygon contains runway, aprons and facilities; taxiways connected; grading follows polygon")

func verify_field_grounding(preview: Node3D) -> void:
	var vertices: PackedVector3Array = preview.terrain.get_child(0).mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for installation in preview.site_layout.field_installations:
		var node = preview.get_node(installation.id)
		var found_vertex = false
		for vertex in vertices:
			if is_equal_approx(vertex.x, node.position.x) and is_equal_approx(vertex.z, node.position.z):
				assert(absf(vertex.y - node.position.y) < 0.002, "Exterior poles must follow the rendered terrain after switching modes")
				found_vertex = true
				break
		assert(found_vertex, "Pilot coordinates must remain on the shared terrain grid")
	print("PASS: exterior fixed-phone poles grounded on " + preview.terrain.name)

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
		var terrain_before: bool = preview.geographic
		mouse_motion(0, Vector2.ZERO, ui_point)
		mouse_button(MOUSE_BUTTON_LEFT, true, ui_point)
		assert(preview.drag_button == MOUSE_BUTTON_NONE)
		mouse_button(MOUSE_BUTTON_LEFT, false, ui_point)
		assert(preview.geographic != terrain_before, "Terrain button must still receive clicks")
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
	assert(preview.camera.position.is_equal_approx(preview.vector(preview.site_layout.camera.close)))
	assert(preview.camera_target.is_equal_approx(preview.vector(preview.site_layout.camera.target)))
	print("PASS: mouse pan/orbit through viewport, drag release, focus loss, pitch limits and home")
	return true


func verify_mission_vignettes(preview: Node3D) -> void:
	preview.load_case("case_001")
	preview.playing = false
	preview.set_drone_positions(false)
	preview.detected_ids.clear()
	var actor = preview.objects[10]
	var mission = {"id":"fixture-impact", "object_id":actor.object_id, "asset_id":"fixture", "kind":"impact_vignette", "phase":"approach", "phase_start_ms":1000, "phase_end_ms":2000}
	preview.monitor_exercise = {"assets":[{"id":"fixture", "position":[0,0,0]}]}
	preview.simulation_missions = [mission]
	preview.elapsed_ms = 1500
	preview.update_mission_vignettes()
	var marker = preview.mission_nodes[mission.id]
	assert(not marker.visible and actor.node.visible)
	mission.phase = "finale"
	preview.update_mission_vignettes()
	var halfway: Vector3 = actor.node.position
	assert(marker.visible and not marker.get_node("Label").visible)
	assert(not marker.get_node("Payload").visible and not marker.get_node("Outcome").visible)
	preview.update_mission_vignettes()
	assert(actor.node.position.is_equal_approx(halfway), "Paused time must freeze illustrative descent")
	preview.elapsed_ms = 1750
	preview.update_mission_vignettes()
	assert(actor.node.position.y < halfway.y, "Fixed impact vignette descends")
	preview.elapsed_ms = 1500
	preview.update_mission_vignettes()
	assert(actor.node.position.is_equal_approx(halfway), "Seek restores the same authored phase")
	preview.detected_ids[actor.object_id] = true
	preview.update_mission_vignettes()
	assert(marker.get_node("Label").visible)
	preview.detected_ids.clear()
	preview.set_drone_positions(true)
	preview.update_mission_vignettes()
	assert(marker.get_node("Label").visible)
	preview.set_drone_positions(false)
	mission.kind = "drop_vignette"
	preview.update_mission_vignettes()
	var payload = marker.get_node("Payload")
	var payload_before: Vector3 = payload.position
	var retreat_before: Vector3 = actor.node.position
	assert(payload.visible)
	preview.elapsed_ms = 1750
	preview.update_mission_vignettes()
	assert(payload.position.y < payload_before.y and actor.node.position.x > retreat_before.x)
	for phase in ["complete", "partial", "prevented"]:
		mission.phase = phase
		preview.update_mission_vignettes()
		assert(marker.get_meta("phase") == phase)
		assert(marker.get_node("Outcome").visible and not payload.visible)
		assert(not marker.get_node("Label").visible, "Outcome does not grant detection")
	preview.simulation_missions.clear()
	preview.update_mission_vignettes()
	assert(preview.mission_nodes.is_empty(), "Reset removes all mission effect nodes")
	preview.load_case("case_001")
	assert(preview.simulation_missions.is_empty() and preview.mission_nodes.is_empty())
	var raw = Vector3(1,80,2)
	preview.geographic = false
	assert(preview.display_position(raw) == raw)
	preview.geographic = true
	assert(preview.display_position(raw).y == raw.y + preview.terrain_data.display_airspace_offset_m)
	print("PASS: fixed impact/drop/retreat phases, outcome presets, detection-gated labels, pause/seek/reset and display-only altitude")
