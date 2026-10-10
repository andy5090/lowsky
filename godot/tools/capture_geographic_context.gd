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
	preview.elapsed_ms = minf(435000, float(preview.world_data.duration_ms) * 0.65)
	var context = preview.terrain.get_node("GeographicContext")
	print("Surroundings: %s trees, %s road ways, %s buildings" % [context.get_meta("tree_count"), context.get_meta("road_count"), context.get_meta("building_count")])
	preview.toggle_ui_panel()
	var views = [
		{"name": "korea-forest", "eye": Vector3(-2200, 220, -1000), "target": Vector3(-3100, 30, -2100)},
		{"name": "korea-town", "eye": Vector3(-1550, 170, 1700), "target": Vector3(-800, 20, 700)},
	]
	for view in views:
		view.eye.y += preview.terrain_surface_height(view.eye.x, view.eye.z)
		view.target.y += preview.terrain_surface_height(view.target.x, view.target.z)
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
