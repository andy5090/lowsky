extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func control(command: Dictionary) -> Dictionary:
	var base_url = "http://127.0.0.1:8765"
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--monitor-port="):
			base_url = "http://127.0.0.1:" + argument.trim_prefix("--monitor-port=")
	var request = HTTPRequest.new()
	root.add_child(request)
	request.timeout = 2
	var error = request.request(base_url + "/api/control", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(command))
	assert(error == OK)
	var response = await request.request_completed
	request.queue_free()
	assert(response[0] == HTTPRequest.RESULT_SUCCESS and response[1] == 200)
	return JSON.parse_string(response[3].get_string_from_utf8())

func verify() -> void:
	await control({"action": "case", "case_id": "case_002"})
	await control({"action": "seek", "at_ms": 0})
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await create_timer(0.8).timeout
	assert(preview.monitor_mode and preview.monitor_connected)
	assert(preview.case_id == "case_002" and preview.elapsed_ms == 0)
	assert(not preview.show_drone_positions)
	assert(preview.drone_overlay.markers().is_empty(), "No labels before any received detection")
	for item in preview.objects:
		assert(not item.label.visible)
		assert(item.node.visible, "Physical drone models remain visible without detection labels")
	await control({"action": "seek", "at_ms": 270000})
	await create_timer(0.4).timeout
	var received_count: int = preview.detected_ids.size()
	assert(received_count > 0 and received_count < preview.objects.size())
	assert(preview.drone_overlay.markers().size() == received_count)
	preview.set_drone_positions(true)
	assert(preview.drone_overlay.markers().size() == preview.objects.size())
	for marker in preview.drone_overlay.markers():
		assert(marker.sim)
	preview.set_drone_positions(false)
	assert(preview.drone_overlay.markers().size() == received_count)
	await control({"action": "seek", "at_ms": 0})
	await create_timer(0.4).timeout
	assert(preview.drone_overlay.markers().is_empty(), "Rewind clears all detection labels")
	await control({"action": "seek", "at_ms": 435000})
	await create_timer(0.4).timeout
	assert(preview.camera.position == preview.vector(preview.site_layout.camera.overview))
	assert(preview.drone_overlay.mouse_filter == Control.MOUSE_FILTER_IGNORE)
	assert(preview.drone_overlay.markers().size() == preview.detected_ids.size(), "Overview labels follow received detections")
	var before_position: Vector3 = preview.objects[0].node.position
	preview.toggle_follow()
	assert(preview.follow_drone)
	await control({"action": "speed", "speed": 2})
	await control({"action": "play"})
	await create_timer(0.8).timeout
	assert(preview.elapsed_ms > 435000 and preview.monitor_playing)
	assert(preview.objects[0].node.position != before_position)
	assert(preview.camera_target.is_equal_approx(preview.objects[0].node.position))
	assert(preview.camera.position.distance_to(preview.camera_target) < 10)
	await control({"action": "pause"})
	await create_timer(0.4).timeout
	var paused: float = preview.elapsed_ms
	var paused_position: Vector3 = preview.objects[0].node.position
	await create_timer(0.4).timeout
	assert(preview.elapsed_ms == paused and not preview.monitor_playing)
	assert(preview.objects[0].node.position == paused_position)
	preview.toggle_follow()
	assert(not preview.follow_drone)
	assert(preview.drone_overlay.markers().size() == preview.detected_ids.size())
	preview.toggle_follow()
	preview.pan_camera(Vector2(5, 0))
	assert(not preview.follow_drone, "Manual camera movement must exit follow")
	await control({"action": "case", "case_id": "case_003"})
	await control({"action": "seek", "at_ms": 150000})
	# Case loading and a 240-track response can exceed one poll interval.
	var sync_deadline = Time.get_ticks_msec() + 10000
	while (preview.case_id != "case_003" or preview.elapsed_ms != 150000) and Time.get_ticks_msec() < sync_deadline:
		await create_timer(0.1).timeout
	if preview.case_id != "case_003" or preview.elapsed_ms != 150000:
		push_error("Case switch did not synchronize: %s / %s" % [preview.case_id, preview.elapsed_ms])
		quit(1)
		return
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	preview._unhandled_input(event)
	assert(preview.elapsed_ms == 150000, "Local replay keys must not override server")
	# Simulate transport failure without terminating the user's monitor server.
	preview.receive_monitor_clock(HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), PackedByteArray())
	preview._process(1)
	assert(not preview.monitor_connected and preview.elapsed_ms == 150000)
	assert(preview.drone_overlay.markers().is_empty())
	for item in preview.objects:
		assert(not item.label.visible)
		assert(item.node.visible, "Physical drone models remain visible without detection labels")
	await control({"action": "case", "case_id": "case_001"})
	await control({"action": "speed", "speed": 1})
	print("PASS: HTTP shared clock, case/seek/speed/play/pause, detection-only labels, explicit SIM switch, rewind clearing, follow camera, local control isolation and disconnect freeze")
	preview.queue_free()
	await process_frame
	quit()
