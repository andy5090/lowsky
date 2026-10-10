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
	await control({"action": "seek", "at_ms": 65000})
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await create_timer(0.8).timeout
	assert(preview.monitor_mode and preview.monitor_connected)
	assert(preview.case_id == "case_002" and preview.elapsed_ms == 65000)
	assert(preview.camera.position == preview.vector(preview.site_layout.camera.overview))
	assert(preview.drone_overlay.mouse_filter == Control.MOUSE_FILTER_IGNORE)
	assert(preview.drone_overlay.markers().size() == preview.objects.size(), "All drones need visible overview markers")
	var before_position: Vector3 = preview.objects[0].node.position
	preview.toggle_follow()
	assert(preview.follow_drone)
	await control({"action": "speed", "speed": 2})
	await control({"action": "play"})
	await create_timer(0.8).timeout
	assert(preview.elapsed_ms > 65000 and preview.monitor_playing)
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
	assert(preview.drone_overlay.markers().size() == preview.objects.size())
	preview.toggle_follow()
	preview.pan_camera(Vector2(5, 0))
	assert(not preview.follow_drone, "Manual camera movement must exit follow")
	await control({"action": "case", "case_id": "case_003"})
	await control({"action": "seek", "at_ms": 150000})
	await create_timer(0.5).timeout
	assert(preview.case_id == "case_003" and preview.elapsed_ms == 150000)
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	preview._unhandled_input(event)
	assert(preview.elapsed_ms == 150000, "Local replay keys must not override server")
	# Simulate transport failure without terminating the user's monitor server.
	preview.receive_monitor_clock(HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), PackedByteArray())
	preview._process(1)
	assert(not preview.monitor_connected and preview.elapsed_ms == 150000)
	await control({"action": "case", "case_id": "case_001"})
	await control({"action": "speed", "speed": 1})
	print("PASS: HTTP shared clock, case/seek/speed/play/pause, visible overview markers, follow camera, local control isolation and disconnect freeze")
	preview.queue_free()
	await process_frame
	quit()
