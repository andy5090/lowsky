extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	preview.playing = false
	preview.show_overview()
	preview.elapsed_ms = 0
	preview._process(0)
	assert(preview.detected_ids.is_empty())
	assert(preview.drone_overlay.markers().is_empty())
	# Use the fixture's delivery boundary; paced scenarios now begin at 04:30.
	var first_delivery = INF
	for observation in preview.public_data.observations:
		if observation.get("detected", true):
			first_delivery = minf(first_delivery, float(observation.available_at_ms))
	assert(is_finite(first_delivery))
	preview.elapsed_ms = first_delivery - 1
	preview._process(0)
	assert(preview.detected_ids.is_empty(), "No label may precede the first received report")
	preview.elapsed_ms = first_delivery
	preview._process(0)
	assert(not preview.detected_ids.is_empty() and preview.detected_ids.size() < preview.objects.size())
	for item in preview.objects:
		assert(item.label.visible == preview.detected_ids.has(item.object_id))
	preview.set_drone_positions(true)
	for item in preview.objects:
		assert(item.label.visible and item.label.text.begins_with("AUTHOR "))
	preview.set_drone_positions(false)
	preview.elapsed_ms = 0
	preview._process(0)
	assert(preview.drone_overlay.markers().is_empty())
	# Controlled public inputs prove labels never derive detection from world paths.
	var object_id = preview.objects[0].object_id
	preview.public_data = {
		"freshness_ms": 45000, "source_ids": ["channel_a"],
		"source_health": [{"source_id": "channel_a", "observed_at_ms": 0, "available_at_ms": 0, "status": "online"}],
		"observations": [{"object_id": object_id, "source_id": "channel_a", "observed_at_ms": 1000, "available_at_ms": 2000}]
	}
	preview.elapsed_ms = 1000
	preview._process(0)
	assert(preview.detected_ids.is_empty(), "Future delivery is not a detection")
	preview.elapsed_ms = 2000
	preview._process(0)
	assert(preview.detected_ids.has(object_id))
	preview.public_data.observations[0].detected = false
	preview._process(0)
	assert(preview.detected_ids.is_empty(), "Negative reports do not grant labels")
	preview.public_data.observations[0].detected = true
	preview.public_data.source_health[0].status = "offline"
	preview._process(0)
	assert(preview.detected_ids.is_empty(), "Offline source does not grant current detection")
	preview.public_data.source_health[0].status = "online"
	preview.elapsed_ms = 47000
	preview._process(0)
	assert(preview.detected_ids.is_empty(), "Expired detection hides labels")
	preview.load_case("case_003")
	assert(preview.detected_ids.is_empty())
	for item in preview.objects:
		assert(not item.label.visible)
	preview.monitor_mode = true
	var state = {"case_id": "case_003", "at_ms": 50000, "playing": false, "speed": 1,
		"tracks": [{"object_id": preview.objects[0].object_id, "last_known": true}]}
	preview.receive_monitor_clock(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify(state).to_utf8_buffer())
	assert(preview.detected_ids.is_empty(), "Last-known track cannot label the moving author body")
	state.tracks[0].last_known = false
	preview.receive_monitor_clock(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify(state).to_utf8_buffer())
	assert(preview.objects[0].label.visible)
	preview.monitor_received_at = Time.get_ticks_msec() - 1501
	preview._process(0)
	assert(not preview.objects[0].label.visible, "Stale connection hides labels")
	print("PASS: standalone and shared detection visibility, delayed/negative/offline/expired reports, SIM override, rewind/case reset, last-known and disconnect hiding")
	preview.queue_free()
	await process_frame
	quit()
