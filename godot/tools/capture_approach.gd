extends SceneTree
## Windowed captures of the approach overview and a launching drone facing the MDL.
## Run without --headless: Godot --path godot --script res://tools/capture_approach.gd

func _initialize() -> void:
	call_deferred("capture")

func capture() -> void:
	root.size = Vector2i(1440, 900)
	var preview = load("res://preview.tscn").instantiate()
	root.add_child(preview)
	await process_frame
	preview.playing = false
	# Use the panel toggle so the captured control state matches the author view.
	var toggle: CheckButton = preview.ui_body.find_children("*", "CheckButton", true, false)[0]
	toggle.button_pressed = true
	assert(preview.show_drone_positions)
	var item: Dictionary = preview.world_data.objects.filter(func(entry): return entry.route.corridor_id == "central")[0]
	preview.elapsed_ms = float(item.route.launch_ms) + 20000.0
	preview.show_approach_view()
	await save(preview, "godot-approach.png")
	# Close behind a drone that has just left the central launch area, looking south
	# across the DMZ northern limit toward the MDL.
	preview.toggle_ui_panel()
	var drone: Dictionary = preview.objects.filter(func(entry): return entry.object_id == item.object_id)[0]
	preview.elapsed_ms = float(item.route.launch_ms) + 4000.0
	preview._process(0)
	# Same reduced world label the follow camera uses; the screen callout stays readable.
	drone.label.pixel_size *= 0.1
	var position: Vector3 = drone.node.position
	preview.camera_target = position
	var span = float(drone.node.get_meta("horizontal_span_m"))
	preview.camera.position = position + Vector3(0.5, 0.9, -1.8) * span
	preview.camera.look_at(position)
	await save(preview, "godot-mdl.png")
	quit()

func save(preview: Node3D, filename: String) -> void:
	for frame in range(10):
		await process_frame
	await RenderingServer.frame_post_draw
	var path = ProjectSettings.globalize_path("res://../.local/" + filename)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	assert(root.get_texture().get_image().save_png(path) == OK)
	print("Screenshot: " + path)
