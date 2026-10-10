extends SceneTree
var base_url = "http://127.0.0.1:8766"
func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--monitor-port="):
			base_url = "http://127.0.0.1:" + argument.trim_prefix("--monitor-port=")
	call_deferred("verify")
func api(path: String, command = null) -> Dictionary:
	var request = HTTPRequest.new()
	root.add_child(request)
	request.timeout = 5
	request.request(base_url + path, ["Content-Type: application/json"], HTTPClient.METHOD_GET if command == null else HTTPClient.METHOD_POST, "" if command == null else JSON.stringify(command))
	var response = await request.request_completed
	request.queue_free()
	if response[0] != HTTPRequest.RESULT_SUCCESS or response[1] != 200:
		push_error("Exercise API failed %s" % response[1])
		quit(1)
		return {}
	return JSON.parse_string(response[3].get_string_from_utf8())
func verify() -> void:
	await api("/api/control", {"action":"case","case_id":"case_001"})
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await create_timer(0.8).timeout
	assert(preview.monitor_connected)
	assert(preview.objects.size() == preview.world_data.objects.size())
	for item in preview.objects:
		assert(item.node.visible, "All physical drones remain visible before detection")
		assert(not item.label.visible, "Only labels await detection")
	var state = await api("/api/control", {"action":"seek","at_ms":540000})
	var object_id = "object_13"
	assert(object_id in state.exercise.eligible_objects)
	state = await api("/api/control", {"action":"exercise_branch","run_id":state.run_id,"object_id":object_id,"asset_id":"admin_1","branch_id":"hold","confirm":true})
	assert(state.exercise.selection.status == "pending")
	await api("/api/control", {"action":"speed","speed":4})
	await api("/api/control", {"action":"play"})
	await create_timer(1.7).timeout
	assert(preview.monitor_playing)
	assert(preview.monitor_exercise.selection.status == "applied")
	assert(preview.exercise_marker.visible)
	assert("RESTRICTED" in preview.exercise_marker.text)
	var selected = preview.objects.filter(func(item): return item.object_id == object_id)[0]
	var position: Vector3 = selected.node.position
	var before: float = preview.elapsed_ms
	await create_timer(0.5).timeout
	assert(preview.elapsed_ms > before, "Clock advances during scripted hold")
	assert(selected.node.position.is_equal_approx(position), "Only selected aircraft holds its position")
	state = await api("/api/control", {"action":"pause"})
	assert(state.exercise.assets.filter(func(a): return a.id == "admin_1")[0].status == "restricted")
	await api("/api/control", {"action":"reset"})
	await create_timer(0.4).timeout
	assert(preview.monitor_exercise.selection == null)
	assert(not preview.exercise_marker.visible)
	for item in preview.objects:
		assert(item.node.visible and not item.label.visible)
	assert(await verify_missions(preview))
	verify_visual_cast(preview)
	print("PASS: physical drones independent of detection; delayed branch changes motion and facility status; clock continues; reset clears branch")
	preview.queue_free()
	await process_frame
	quit()


func sync_paused(preview, at_ms: int) -> Dictionary:
	var state = await api("/api/control", {"action":"seek", "at_ms":at_ms})
	var deadline = Time.get_ticks_msec() + 5000
	while int(preview.elapsed_ms) != at_ms and Time.get_ticks_msec() < deadline:
		await create_timer(0.05).timeout
	assert(int(preview.elapsed_ms) == at_ms)
	preview._process(0)
	return state

func verify_missions(preview) -> bool:
	var state = await sync_paused(preview, 680000)
	assert(state.exercise.missions.size() == 2)
	var impact = preview.mission_nodes["vignette_impact"]
	assert(impact.get_meta("phase") == "finale" and impact.visible)
	var actor = preview.objects.filter(func(item): return item.object_id == "object_11")[0]
	var before: Vector3 = actor.node.position
	await create_timer(0.3).timeout
	assert(actor.node.position.is_equal_approx(before), "Paused shared clock freezes finale")
	state = await sync_paused(preview, 690000)
	assert(impact.get_meta("phase") == "complete" and impact.get_node("Damage").visible)
	assert(impact.get_node("Flash").visible)
	assert(preview.facility_nodes["hangar_1"].get_meta("charred"))
	assert(state.exercise.assets.filter(func(a): return a.id == "hangar_1")[0].status == "unavailable")
	await sync_paused(preview, 691500)
	assert(not impact.get_node("Flash").visible and impact.get_node("Damage/Debris").is_visible_in_tree())
	var flame = impact.get_node("Damage/Flame0")
	var smoke = impact.get_node("Damage/Smoke10")
	var flame_pose: Transform3D = flame.transform
	var smoke_pose: Transform3D = smoke.transform
	var flame_clock: float = flame.material_override.get_shader_parameter("clock")
	var smoke_clock: float = smoke.material_override.get_shader_parameter("clock")
	await create_timer(0.3).timeout
	assert(flame.transform.is_equal_approx(flame_pose) and smoke.transform.is_equal_approx(smoke_pose), "Paused clock freezes fire and smoke")
	assert(flame.material_override.get_shader_parameter("clock") == flame_clock and smoke.material_override.get_shader_parameter("clock") == smoke_clock, "Paused clock freezes animated sprite textures")
	if "--capture-results" in OS.get_cmdline_user_args():
		preview.stop_follow()
		preview.camera_target = Vector3(20, 20, -260)
		preview.camera.position = Vector3(170, 120, -60)
		preview.camera.look_at(preview.camera_target)
		await process_frame
		await RenderingServer.frame_post_draw
		assert(preview.ui_panel.get_global_rect().end.y <= root.size.y - 50, "Enlarged panel fits viewport with scroll")
		assert(preview.ui_title.get_theme_font_size("font_size") == 36)
		var panel_path = ProjectSettings.globalize_path("res://../.local/mission-panel.png")
		assert(root.get_texture().get_image().save_png(panel_path) == OK)
		preview.toggle_ui_panel()
		await process_frame
		await process_frame
		await RenderingServer.frame_post_draw
		var capture_path = ProjectSettings.globalize_path("res://../.local/mission-damage.png")
		assert(root.get_texture().get_image().save_png(capture_path) == OK)
		print("Screenshot: " + capture_path)
	await sync_paused(preview, 680000)
	assert(not impact.get_node("Damage").visible and not preview.facility_nodes["hangar_1"].get_meta("charred"), "Rewind restores intact facility")
	await sync_paused(preview, 691500)
	# Billboard rotation follows the camera; animation state follows only replay time.
	assert(flame.position.is_equal_approx(flame_pose.origin) and smoke.position.is_equal_approx(smoke_pose.origin), "Seeking to same time reproduces particle positions")
	assert(flame.scale.is_equal_approx(flame_pose.basis.get_scale()) and smoke.scale.is_equal_approx(smoke_pose.basis.get_scale()))
	assert(flame.material_override.get_shader_parameter("clock") == flame_clock and smoke.material_override.get_shader_parameter("clock") == smoke_clock, "Seeking reproduces animated texture state")
	await sync_paused(preview, 710000)
	var drop = preview.mission_nodes["vignette_drop"]
	assert(drop.get_meta("phase") == "finale" and drop.get_node("Payload").visible)
	await sync_paused(preview, 720000)
	assert(drop.get_meta("phase") == "complete" and not drop.get_node("Payload").visible)
	assert(drop.get_node("Damage").visible and preview.facility_nodes["admin_1"].get_meta("charred"))
	for branch in ["hold", "withdraw"]:
		await api("/api/control", {"action":"reset"})
		state = await sync_paused(preview, 540000)
		state = await api("/api/control", {"action":"exercise_branch", "run_id":state.run_id, "object_id":"object_11", "asset_id":"hangar_1", "branch_id":branch, "confirm":true})
		await api("/api/control", {"action":"speed", "speed":4})
		await api("/api/control", {"action":"play"})
		await create_timer(1.7).timeout
		await api("/api/control", {"action":"pause"})
		await create_timer(0.4).timeout
		impact = preview.mission_nodes["vignette_impact"]
		assert(impact.get_meta("phase") == ("partial" if branch == "hold" else "prevented"))
		assert(not impact.get_node("Damage").visible and not impact.get_node("Flash").visible and not impact.get_node("Payload").visible)
		assert(not preview.facility_nodes["hangar_1"].get_meta("charred"))
	await api("/api/control", {"action":"reset"})
	await create_timer(0.4).timeout
	for marker in preview.mission_nodes.values():
		assert(not marker.visible, "Reset clears visible mission and outcome effects")
	for facility in preview.facility_nodes.values():
		assert(not facility.get_meta("charred", false), "Reset restores facility materials")
	assert(preview.detected_ids.is_empty())
	print("PASS: live shared-clock impact/drop finales, frozen pause, scripted partial/prevented outcomes and reset")
	return true

func verify_visual_cast(preview) -> void:
	preview.set_process(false)
	preview.monitor_request.cancel_request()
	var item: Dictionary = preview.objects[0]
	var previous: Node3D = item.node
	var label: Label3D = item.label
	var pose: Transform3D = previous.transform
	var frames: Array = item.keyframes
	var alternatives: Array = preview.display_profiles.airframes.keys().filter(func(id): return id != previous.get_meta("airframe_id"))
	preview.follow_drone = true
	preview.apply_visual_cast({"signature":"verify-one", "objects":[{"object_id":item.object_id, "airframe_id":alternatives[0]}]})
	assert(item.node != previous and item.node.get_meta("airframe_id") == alternatives[0])
	assert(item.label == label and label.get_parent() == item.node and item.node.transform == pose and item.keyframes == frames and preview.follow_drone)
	var replacement: Node3D = item.node
	preview.apply_visual_cast({"signature":"verify-one", "objects":[{"object_id":item.object_id, "airframe_id":alternatives[0]}]})
	assert(item.node == replacement, "Same cast does not rebuild models")
	preview.apply_visual_cast({"signature":"verify-two", "objects":[{"object_id":item.object_id, "airframe_id":alternatives[1]}]})
	assert(item.node != replacement and item.node.get_meta("airframe_id") == alternatives[1])
	preview.apply_visual_cast({})
	assert(item.node.get_meta("airframe_id") == preview.world_data.objects[0].visual.airframe_id, "Fixture restores original model")
	print("PASS: changed cast replaces geometry, repeated cast is stable, fixture restores models; labels, paths and follow preserved")
