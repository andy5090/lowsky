extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	preview.playing = false
	preview.elapsed_ms = 0
	preview._process(0)
	assert(preview.objects.size() > 1)
	assert(preview.selected_drone_index == 0)
	assert(not preview.follow_drone)
	assert(not preview.previous_drone_button.disabled and not preview.next_drone_button.disabled)
	preview.detected_ids.clear()
	preview.update_drone_labels()
	var first_position: Vector3 = preview.objects[0].node.position
	preview.toggle_follow()
	assert(preview.follow_drone and preview.camera_target == first_position)
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_BRACKETRIGHT
	preview._unhandled_input(event)
	assert(preview.selected_drone_index == 1)
	assert(preview.camera_target == preview.objects[1].node.position)
	assert(preview.camera_target != first_position)
	assert(preview.objects[1].label.pixel_size < preview.objects[0].label.pixel_size)
	assert(preview.selected_drone_label.text.contains(preview.objects[1].object_id))
	assert(preview.selected_drone_label.text.begins_with("CAMERA / SIM:"))
	for item in preview.objects:
		assert(not item.label.visible and not item.sim, "Camera selection must never grant detection labels or SIM positions")
	preview.toggle_follow()
	assert(not preview.follow_drone and preview.selected_drone_index == 1)
	assert(preview.objects[1].label.pixel_size == preview.objects[0].label.pixel_size)
	preview.toggle_follow()
	assert(preview.follow_drone and preview.camera_target == preview.objects[1].node.position)
	preview.pan_camera(Vector2(1, 1))
	assert(not preview.follow_drone and preview.selected_drone_index == 1)
	preview.select_drone(-1)
	assert(preview.selected_drone_index == 0)
	preview.select_drone(-1)
	assert(preview.selected_drone_index == preview.objects.size() - 1)
	preview.select_drone(1)
	assert(preview.selected_drone_index == 0)
	preview.orbit_camera(Vector2(1, 1))
	assert(not preview.follow_drone)
	preview.select_drone(3)
	preview.load_case("case_003")
	assert(preview.objects.size() == 240)
	assert(preview.selected_drone_index == 0 and not preview.follow_drone)
	preview.select_drone(-1)
	assert(preview.selected_drone_index == 239 and preview.follow_drone)
	preview.load_case("case_001")
	assert(preview.selected_drone_index == 0 and not preview.follow_drone)
	preview.detected_ids[preview.objects[0].object_id] = true
	preview.update_drone_labels()
	preview.select_drone(1)
	assert(preview.objects[0].label.visible and not preview.objects[1].label.visible)
	assert(not preview.show_drone_positions)
	preview.set_drone_positions(true)
	assert(preview.objects[1].label.visible)
	preview.set_drone_positions(false)
	assert(not preview.objects[1].label.visible)
	# The camera's close view must not change the physical model scale.
	preview.objects[1].node.get_node("Visual").rotation = Vector3.ZERO
	preview.pose_drone(preview.objects[1].node, Vector3.FORWARD, 0)
	# Measure at the origin: 18 km schematic coordinates lose sub-millimeter precision.
	var saved_position: Vector3 = preview.objects[1].node.position
	preview.objects[1].node.position = Vector3.ZERO
	var bounds: Array = preview.collect_bounds(preview.objects[1].node, Transform3D.IDENTITY)
	var combined: AABB = bounds[0]
	for bound in bounds:
		combined = combined.merge(bound)
	assert(absf(maxf(combined.size.x, combined.size.z) - 0.6) < 0.001)
	preview.objects[1].node.position = saved_position
	var small_distance: float = preview.camera.position.distance_to(preview.camera_target)
	preview.select_drone(2)
	assert(preview.objects[3].node.get_meta("airframe_id") == "geran_2")
	assert(preview.camera.position.distance_to(preview.camera_target) > small_distance * 4)
	assert(preview.selected_drone_label.text.contains("Geran-2"))
	var saved_objects: Array = preview.objects.duplicate()
	preview.objects.clear()
	preview.select_drone(1)
	assert(not preview.follow_drone and preview.selected_drone_index == 0)
	assert(preview.previous_drone_button.disabled and preview.next_drone_button.disabled and preview.follow_button.disabled)
	preview.toggle_follow()
	assert(not preview.follow_drone)
	preview.objects.append_array(saved_objects)
	print("PASS: previous/next camera selection, wrap, F toggle, manual cancellation, 240-object case reset, empty controls, received-only labels, and 0.6 m scale")
	preview.queue_free()
	await process_frame
	quit()
