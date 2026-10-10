extends SceneTree

var base_url := "http://127.0.0.1:8766"

func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--monitor-port="):
			base_url = "http://127.0.0.1:" + argument.trim_prefix("--monitor-port=")
	call_deferred("verify")

func api(path: String, command = null) -> Dictionary:
	var request := HTTPRequest.new()
	root.add_child(request)
	request.timeout = 3
	var method = HTTPClient.METHOD_GET if command == null else HTTPClient.METHOD_POST
	var body = "" if command == null else JSON.stringify(command)
	assert(request.request(base_url + path, ["Content-Type: application/json"], method, body) == OK)
	var response = await request.request_completed
	request.queue_free()
	if response[0] != HTTPRequest.RESULT_SUCCESS or response[1] < 200 or response[1] >= 300:
		push_error("Unexpected API response: %s" % response[1])
		quit(1)
		return {}
	return JSON.parse_string(response[3].get_string_from_utf8())

func verify() -> void:
	# Run only against an isolated rules-mode server, never the user's active replay.
	var status = await api("/api/assessment")
	assert(status.mode == "rules", "Use LOW_SKY_AGENT_MODEL='' on the isolated test server")
	var clock = await api("/api/control", {"action":"case", "case_id":"case_001"})
	await api("/api/decisions", {"action":"configure", "run_id":clock.run_id, "enabled":true, "language":"en"})
	await api("/api/control", {"action":"speed", "speed":1})
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await create_timer(0.8).timeout
	assert(preview.monitor_connected)
	await api("/api/control", {"action":"start_test", "seed":42})
	var event: Dictionary = {}
	for _attempt in range(150):
		await create_timer(0.2).timeout
		var decisions = await api("/api/decisions")
		if decisions.events.size() > 0 and decisions.events[0].status == "ready":
			event = decisions.events[0]
			break
	assert(not event.is_empty(), "First received event must create a decision checkpoint")
	await create_timer(0.5).timeout
	assert(preview.monitor_playing)
	assert(preview.monitor_test_run.get("seed") == 42, "Godot must identify the shared seeded test")
	assert(int(preview.elapsed_ms) >= int(event.at_ms))
	var frozen: float = preview.elapsed_ms
	await create_timer(0.4).timeout
	assert(preview.elapsed_ms > frozen, "Godot must advance while awaiting human confirmation")
	await api("/api/decisions", {"action":"confirm", "run_id":event.run_id, "event_id":event.id,
		"evidence_version":event.evidence_version, "option_id":"hold_review", "confirm":true,
		"reviewer":"integration-test", "reason":"Verify evidence review does not stop shared playback"})
	await create_timer(0.7).timeout
	assert(preview.elapsed_ms > frozen, "Godot must keep advancing after evidence-review confirmation")
	await api("/api/control", {"action":"pause"})
	await api("/api/control", {"action":"speed", "speed":1})
	var state = await api("/api/state")
	await create_timer(0.5).timeout
	var received_ids: Dictionary = {}
	for track in state.tracks:
		if not track.last_known:
			received_ids[str(track.object_id)] = true
	assert(preview.detected_ids == received_ids, "Godot labels must match generated received evidence")
	print("PASS: seeded test matches Godot seed and received labels, advances during event review and after confirmation")
	preview.queue_free()
	await process_frame
	quit()
