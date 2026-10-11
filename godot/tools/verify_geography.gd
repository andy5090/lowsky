extends SceneTree
## MDL/DMZ reference ribbons, author-only launch areas and the approach camera preset.

## English until the monitor selects Korean (verify_language covers the switch).
const EXPECTED_LABELS = {"mdl": "MDL", "dmz_south": "DMZ south limit", "dmz_north": "DMZ north limit"}
## Northernmost reach each line must exceed (local Z, metres; the DMZ south limit stays near -41.3 km).
const NORTH_OF = {"mdl": -43000.0, "dmz_south": -41000.0, "dmz_north": -43000.0}

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await process_frame
	preview.playing = false
	var geography: Node3D = preview.geography
	assert(is_instance_valid(geography), "Geography resolves through data_root/../../geography")
	var corridors = preview.read_json(preview.data_root.path_join("../../geography/approach_corridors.json")).corridors
	assert(corridors.size() == geography.corridors.size() and corridors.size() > 0)
	verify_lines(preview)
	verify_launch_areas(preview, false)
	print("PASS: MDL ribbon north of z=-43000, DMZ limit ribbons, and fixed-size labels; launch areas hidden by default")
	preview.set_drone_positions(true)
	verify_launch_areas(preview, true)
	preview.set_drone_positions(false)
	verify_launch_areas(preview, false)
	print("PASS: launch areas follow the author view toggle")
	assert(preview.camera.far >= 70000)
	var event = InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_B
	preview.set_drone_positions(true)
	preview._unhandled_input(event)
	assert(not preview.follow_drone)
	for corridor in corridors:
		var launch: Vector3 = preview.vector(corridor.launch)
		assert(preview.camera.is_position_in_frustum(launch), "Approach view frames launch area " + corridor.id)
		assert(preview.camera.position.distance_to(launch) < preview.camera.far)
	assert(preview.camera.is_position_in_frustum(Vector3.ZERO), "Approach view frames the site")
	preview.elapsed_ms = 60000
	preview._process(0)
	assert(preview.drone_overlay.markers().size() > 0, "Author markers still project at approach range")
	var approach_buttons = preview.ui_body.find_children("*", "Button", true, false).filter(func(button): return button.text.begins_with("Approach view"))
	assert(approach_buttons.size() == 1)
	preview.set_drone_positions(false)
	print("PASS: approach view [B] frames every launch area and the site within camera.far; overlay markers project")
	for index in range(3):
		preview.toggle_terrain()
		assert(preview.geography == geography and geography.is_inside_tree())
		verify_lines(preview)
		verify_launch_areas(preview, false)
	preview.set_drone_positions(true)
	preview.toggle_terrain()
	verify_launch_areas(preview, true)
	for case_id in ["case_002", "case_003", "case_001"]:
		preview.load_case(case_id)
		assert(preview.geography == geography and geography.is_inside_tree())
		verify_lines(preview)
		verify_launch_areas(preview, true)
	preview.set_drone_positions(false)
	verify_launch_areas(preview, false)
	print("PASS: geography persists across toggle_terrain() and load_case()")
	preview.queue_free()
	await process_frame
	quit()

func verify_lines(preview: Node3D) -> void:
	var geography: Node3D = preview.geography
	for id in EXPECTED_LABELS:
		var ribbon: MeshInstance3D = geography.get_node("Line_" + id)
		assert(ribbon.visible and ribbon.mesh != null and ribbon.mesh.get_surface_count() == 1)
		var vertices: PackedVector3Array = ribbon.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var northern = 0
		for vertex in vertices:
			assert(is_finite(vertex.y))
			if vertex.z < NORTH_OF[id]:
				northern += 1
		assert(northern > 0, "%s ribbon reaches north of z=%d" % [id, NORTH_OF[id]])
		var labels = geography.line_labels.filter(func(label): return label.get_meta("line_id") == id)
		assert(labels.size() >= 2, id + " has labels")
		for label in labels:
			assert(label.text == EXPECTED_LABELS[id] and label.visible and label.fixed_size)

func verify_launch_areas(preview: Node3D, expected: bool) -> void:
	var markers: Array = preview.geography.launch_root.get_children()
	assert(markers.size() == preview.geography.corridors.size())
	for index in markers.size():
		var marker: Node3D = markers[index]
		var corridor: Dictionary = preview.geography.corridors[index]
		assert(marker.is_visible_in_tree() == expected, "Launch areas are author-only")
		assert(is_equal_approx(marker.position.x, corridor.launch[0]) and is_equal_approx(marker.position.z, corridor.launch[2]))
		assert(marker.get_node("Label").text == "Launch area\n· " + corridor.label.en)
