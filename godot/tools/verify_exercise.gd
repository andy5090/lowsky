extends SceneTree
var base_url = "http://127.0.0.1:8766"
func _initialize() -> void:
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
	var state = await api("/api/control", {"action":"seek","at_ms":100000})
	var object_id = state.exercise.eligible_objects[0]
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
	print("PASS: physical drones independent of detection; delayed branch changes motion and facility status; clock continues; reset clears branch")
	preview.queue_free()
	await process_frame
	quit()
