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
	assert(response[0] == HTTPRequest.RESULT_SUCCESS and response[1] >= 200 and response[1] < 300)
	return JSON.parse_string(response[3].get_string_from_utf8())

func verify() -> void:
	# Run only against an isolated rules-mode server, never the user's active replay.
	var status = await api("/api/assessment")
	assert(status.mode == "rules", "Use LOW_SKY_AGENT_MODEL='' on the isolated test server")
	var clock = await api("/api/control", {"action":"case", "case_id":"case_001"})
	await api("/api/decisions", {"action":"configure", "run_id":clock.run_id, "enabled":true, "language":"en"})
	await api("/api/control", {"action":"speed", "speed":4})
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await create_timer(0.8).timeout
	assert(preview.monitor_connected)
	await api("/api/control", {"action":"play"})
	var event: Dictionary = {}
	for _attempt in range(60):
		await create_timer(0.2).timeout
		var decisions = await api("/api/decisions")
		if decisions.events.size() > 0 and decisions.events[0].status == "ready":
			event = decisions.events[0]
			break
	assert(not event.is_empty(), "First received event must create a decision checkpoint")
	await create_timer(0.5).timeout
	assert(not preview.monitor_playing)
	assert(int(preview.elapsed_ms) == int(event.at_ms))
	var frozen: float = preview.elapsed_ms
	await create_timer(0.4).timeout
	assert(preview.elapsed_ms == frozen, "Godot must remain paused before human confirmation")
	await api("/api/decisions", {"action":"confirm", "run_id":event.run_id, "event_id":event.id,
		"evidence_version":event.evidence_version, "option_id":"continue_monitoring", "confirm":true,
		"reviewer":"integration-test", "reason":"Verify shared replay resumes only after explicit confirmation"})
	await create_timer(0.7).timeout
	assert(preview.elapsed_ms > frozen, "Godot must follow confirmed resume")
	await api("/api/control", {"action":"pause"})
	await api("/api/control", {"action":"speed", "speed":1})
	print("PASS: important received event pauses Godot, holds before confirmation, and confirmed choice resumes shared clock")
	preview.queue_free()
	await process_frame
	quit()
