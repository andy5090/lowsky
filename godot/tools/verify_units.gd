extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await process_frame
	preview.playing = false
	preview.monitor_mode = true
	var state = {"case_id":"case_001", "at_ms":0, "playing":false, "speed":1, "tracks":[], "exercise":{"units":[]}}
	send_state(preview, state)
	assert(preview.exercise_units.units.is_empty(), "No personnel appear without explicit placement")
	var unit = {"id":"infantry_1", "kind":"infantry", "label":{"en":"Infantry 1", "ko":"보병 1"}, "position":[40,0,-200], "status":"positioned"}
	state.exercise.units = [unit]
	send_state(preview, state)
	assert(preview.exercise_units.units.size() == 1)
	var person: Node3D = preview.exercise_units.units[unit.id]
	assert(person.get_child_count() > 10 and person.get_node("UnitLabel").text == "Infantry 1")
	verify_ground(preview, person, 40, -200)
	send_state(preview, state)
	assert(preview.exercise_units.units[unit.id] == person, "Unchanged snapshots reuse the personnel model")
	unit.position = [1100,0,1900]
	send_state(preview, state)
	assert(preview.exercise_units.units[unit.id] == person, "Moving preserves unit identity")
	verify_ground(preview, person, 1100, 1900)
	for index in range(3):
		preview.toggle_terrain()
		verify_ground(preview, person, 1100, 1900)
	unit.position = [40,0,-200]
	send_state(preview, state)
	if "--capture-units" in OS.get_cmdline_user_args():
		preview.toggle_ui_panel()
		preview.camera_target = person.position + Vector3(0, 1, 0)
		preview.camera.position = person.position + Vector3(5, 3.2, -8)
		preview.camera.look_at(preview.camera_target)
		for frame in range(3):
			await process_frame
		await RenderingServer.frame_post_draw
		var path = ProjectSettings.globalize_path("res://../.local/infantry-unit.png")
		assert(root.get_texture().get_image().save_png(path) == OK)
		print("Screenshot: " + path)
	var second = unit.duplicate(true)
	second.id = "infantry_2"
	second.position = [42,0,-200]
	state.exercise.units.append(second)
	send_state(preview, state)
	assert(preview.exercise_units.units.size() == 2)
	state.exercise.units = [second]
	send_state(preview, state)
	assert(not preview.exercise_units.units.has("infantry_1") and preview.exercise_units.units.size() == 1)
	state.exercise.units = []
	send_state(preview, state)
	assert(preview.exercise_units.units.is_empty(), "Shared reset clears personnel")
	state.exercise.units = [unit]
	send_state(preview, state)
	preview.load_case("case_002")
	assert(preview.exercise_units.units.is_empty(), "Changing fixture clears personnel")
	await verify_kinds(preview)
	verify_tactics_label(preview)
	print("PASS: explicit personnel add/move/remove/reset, stable identity, exact X/Z, terrain grounding and scene reset")
	print("PASS: four unit kinds with range rings, labels, identity, regrounding, unknown-kind skip and reset; detected labels show tactics lean and training allocation")
	preview.queue_free()
	await process_frame
	quit()

func send_state(preview: Node3D, state: Dictionary) -> void:
	preview.receive_monitor_clock(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify(state).to_utf8_buffer())

func verify_kinds(preview: Node3D) -> void:
	var kinds = [
		{"id":"infantry", "label":{"en":"Infantry", "ko":"보병"}, "budget":12, "display_range_m":0},
		{"id":"radar", "label":{"en":"Military radar", "ko":"군사용 레이더"}, "budget":2, "display_range_m":5000},
		{"id":"detection_phone", "label":{"en":"Drone acoustic listening post", "ko":"드론 청음 초소"}, "budget":10, "display_range_m":1500},
		{"id":"effector_team", "label":{"en":"Effector team", "ko":"대응 팀"}, "budget":4, "display_range_m":2500}]
	var rows = [
		{"id":"infantry_1", "kind":"infantry", "role":"observation_post", "label":{"en":"Infantry 1", "ko":"보병 1"}, "position":[40,0,-200], "status":"positioned", "source":"manual"},
		{"id":"radar_1", "kind":"radar", "role":"surveillance", "label":{"en":"Military radar 1", "ko":"군사용 레이더 1"}, "position":[60,0,-200], "status":"positioned", "source":"proposal"},
		{"id":"detection_phone_1", "kind":"detection_phone", "role":"picket", "label":{"en":"P1 acoustic post", "ko":"P1 드론 청음 초소"}, "position":[50,0,-212], "status":"positioned", "source":"proposal"},
		{"id":"effector_team_1", "kind":"effector_team", "role":"response", "label":{"en":"Effector team 1", "ko":"대응 팀 1"}, "position":[30,0,-215], "status":"positioned", "source":"proposal"},
		{"id":"tank_1", "kind":"tank", "label":{"en":"Tank 1", "ko":"전차 1"}, "position":[0,0,0], "status":"positioned"}]
	var state = {"case_id":"case_002", "at_ms":0, "playing":false, "speed":1, "tracks":[], "exercise":{"units":rows, "unit_kinds":kinds}}
	send_state(preview, state)
	var units: Dictionary = preview.exercise_units.units
	assert(units.size() == 4 and not units.has("tank_1"), "Unknown unit kinds are skipped")
	var expected_ranges = {"infantry_1":0.0, "radar_1":5000.0, "detection_phone_1":1500.0, "effector_team_1":2500.0}
	var nodes: Dictionary = {}
	for row in rows.slice(0, 4):
		var node: Node3D = units[row.id]
		nodes[row.id] = node
		assert(node.get_child_count() > 6, "Each kind has a procedural model: " + row.id)
		assert(node.get_node("UnitLabel").text == row.label.en)
		var ring = node.get_node_or_null("RangeRing")
		if expected_ranges[row.id] > 0:
			assert(ring != null and is_equal_approx(ring.get_meta("range_m"), expected_ranges[row.id]), "Range ring radius follows unit_kinds: " + row.id)
		else:
			assert(ring == null, "Infantry has no range ring")
		verify_ground(preview, node, row.position[0], row.position[2])
	var pole_materials = nodes.detection_phone_1.get_children().filter(func(child): return child is MeshInstance3D).map(func(child): return child.material_override)
	assert(preview.materials.dark_metal in pole_materials, "Acoustic posts reuse the site pole model and scene materials")
	assert(nodes.detection_phone_1.has_node("MicrophoneWindscreen"), "Acoustic posts carry a microphone detail")
	if "--capture-units" in OS.get_cmdline_user_args():
		var center = Vector3(45, preview.terrain_surface_height(45, -207), -207)
		preview.camera_target = center + Vector3(0, 1.5, 0)
		preview.camera.position = center + Vector3(22, 14, -30)
		preview.camera.look_at(preview.camera_target)
		for frame in range(3):
			await process_frame
		await RenderingServer.frame_post_draw
		var path = ProjectSettings.globalize_path("res://../.local/unit-kinds.png")
		assert(root.get_texture().get_image().save_png(path) == OK)
		print("Screenshot: " + path)
	for row in rows.slice(0, 4):
		row.position = [row.position[0] + 900, 0, row.position[2] + 1700]
	send_state(preview, state)
	for row in rows.slice(0, 4):
		assert(units[row.id] == nodes[row.id], "Moving preserves identity: " + row.id)
		verify_ground(preview, nodes[row.id], row.position[0], row.position[2])
		var ring = nodes[row.id].get_node_or_null("RangeRing")
		if ring:
			assert(ring.get_parent() == nodes[row.id] and is_equal_approx(ring.global_position.x, row.position[0]) and is_equal_approx(ring.global_position.z, row.position[2]), "Ring follows unit")
	for index in range(3):
		preview.toggle_terrain()
		for row in rows.slice(0, 4):
			verify_ground(preview, nodes[row.id], row.position[0], row.position[2])
	state.exercise.units = []
	send_state(preview, state)
	assert(preview.exercise_units.units.is_empty(), "Shared reset clears every kind")

func verify_tactics_label(preview: Node3D) -> void:
	var state = {"case_id":"case_002", "at_ms":0, "playing":false, "speed":1, "exercise":{"units":[]},
		"tracks":[{"object_id":"object_11", "last_known":false, "position":[0,120,0]}],
		"tactics":{"scope":"rule_based_training_advice",
			"targets":[{"object_id":"object_11", "identification":{"lean":"decoy_leaning", "profile":"fixed_wing", "verification":"suspected"},
				"response":{"posture":"observe_preserve", "primary":"laser", "allocation":{"id":"a1", "effector_id":"laser", "at_ms":0, "status_at_record":"recommended"}}}],
			"effectors":[{"id":"laser", "label":{"en":"Directed-energy (laser)", "ko":"레이저"}}]}}
	send_state(preview, state)
	var item = find_object(preview, "object_11")
	assert(item.label.visible)
	var text: String = item.label.text
	assert(text.begins_with("DETECTED object_11") and text.contains("DECOY LEANING") and text.contains("FIXED WING"), text)
	assert(text.contains("ALLOCATED: Directed-energy (laser) (training record)"), text)
	state.tactics.effectors = []
	state.tactics.targets[0].identification.profile = "unclassified"
	send_state(preview, state)
	text = item.label.text
	assert(text.contains("ALLOCATED: laser") and not text.contains("UNCLASSIFIED"), text)
	preview.set_drone_positions(true)
	assert(item.label.text == "AUTHOR object_11", "Author view labels stay unchanged")
	preview.set_drone_positions(false)
	state.erase("tactics")
	send_state(preview, state)
	assert(item.label.text == "DETECTED object_11", "Without tactics the detected label is unchanged")

func find_object(preview: Node3D, object_id: String) -> Dictionary:
	for item in preview.objects:
		if item.object_id == object_id:
			return item
	assert(false, "Missing fixture object " + object_id)
	return {}

func verify_ground(preview: Node3D, person: Node3D, x: float, z: float) -> void:
	assert(is_equal_approx(person.position.x, x) and is_equal_approx(person.position.z, z))
	assert(is_equal_approx(person.position.y, preview.terrain_surface_height(x, z)), "Personnel feet match rendered terrain, without aircraft display lift")
