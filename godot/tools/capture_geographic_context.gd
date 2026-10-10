extends SceneTree
## Reproducible close views for forest, mapped town geometry and control states.

func _initialize() -> void:
	call_deferred("capture")

func capture() -> void:
	root.size = Vector2i(1440, 900)
	var preview = load("res://preview.tscn").instantiate()
	root.add_child(preview)
	await process_frame
	preview.playing = false
	preview.elapsed_ms = 65000
	var context = preview.terrain.get_node("GeographicContext")
	print("Surroundings: %s trees, %s road ways, %s buildings" % [context.get_meta("tree_count"), context.get_meta("road_count"), context.get_meta("building_count")])
	preview.toggle_ui_panel()
	var views = [
		{"name": "korea-forest", "eye": Vector3(3600, 235, -2150), "target": Vector3(4100, 130, -2800)},
		{"name": "korea-town", "eye": Vector3(1650, 175, 4100), "target": Vector3(1000, 30, 4400)},
	]
	for view in views:
		preview.camera.position = view.eye
		preview.camera_target = view.target
		preview.camera.look_at(view.target)
		for frame in range(8):
			await process_frame
		await RenderingServer.frame_post_draw
		var path = "res://../artifacts/%s.png" % view.name
		assert(root.get_texture().get_image().save_png(ProjectSettings.globalize_path(path)) == OK)
		print("Saved ", path)
	quit()
