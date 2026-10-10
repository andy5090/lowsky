extends SceneTree

const Geographic = preload("res://geographic_environment.gd")
const Context = preload("res://geographic_context.gd")

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	assert(DisplayServer.get_name() != "headless", "Run with OpenGL: dummy renderer does not retain MultiMesh transforms")
	root.size = Vector2i(1440, 900)
	var preview = load("res://preview.tscn").instantiate()
	root.add_child(preview)
	await process_frame
	await process_frame
	preview.playing = false
	preview.elapsed_ms = minf(435000, float(preview.world_data.duration_ms) * 0.65)
	preview._process(0)
	var context = preview.terrain.get_node("GeographicContext")
	assert(context.get_meta("origin") == preview.terrain_data.origin)
	assert(context.get_meta("tree_count") > 40000 and context.get_meta("tree_count") <= Context.TREE_LIMIT)
	assert(context.get_meta("road_count") > 1000)
	assert(context.get_meta("building_count") > 100)
	var surface: MeshInstance3D = preview.terrain.get_child(0)
	assert(surface.material_override is ShaderMaterial)
	var satellite: Texture2D = surface.material_override.get_shader_parameter("satellite")
	assert(satellite.get_image().has_mipmaps())
	var vertices: PackedVector3Array = surface.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var cover = (load("res://assets/terrain/korea_landcover.png") as Texture2D).get_image()
	var trees = 0
	for chunk in context.get_node("Forest").get_children():
		if chunk.get_meta("is_far_proxy", false):
			var near = chunk.get_parent().get_node(str(chunk.name).trim_prefix("Far_"))
			assert(near.visibility_parent == NodePath("../" + str(chunk.name)))
			assert(chunk.multimesh.instance_count == near.multimesh.instance_count)
			for index in range(0, chunk.multimesh.instance_count, 37):
				assert(chunk.multimesh.get_instance_transform(index) == near.multimesh.get_instance_transform(index))
				assert(chunk.multimesh.get_instance_color(index) == near.multimesh.get_instance_color(index))
			continue
		trees += chunk.multimesh.instance_count
		for index in range(0, chunk.multimesh.instance_count, 19):
			var position: Vector3 = chunk.position + chunk.multimesh.get_instance_transform(index).origin
			var expected = Geographic.surface_height(vertices, 201, 50, position.x, position.z)
			assert(absf(position.y - expected) < 0.002, "Tree must sit on the rendered triangle")
			assert(Geographic.grading_distance(position.x, position.z, preview.site_layout) > 0)
			var pixel = Vector2(position.x, position.z) / 10000.0 + Vector2.ONE * 0.5
			var color = cover.get_pixel(int(pixel.x * cover.get_width()), int(pixel.y * cover.get_height()))
			assert(color.r < 0.025 and absf(color.g - 100.0 / 255) < 0.025 and color.b < 0.025)
	assert(trees == context.get_meta("tree_count"))
	# Shared sampler must agree with independent ray/triangle intersection at non-grid points.
	for point in [Vector2(1349, 1327), Vector2(-4207, -3861), Vector2(2775, -3257)]:
		assert(absf(Geographic.surface_height(vertices, 201, 50, point.x, point.y) - preview.terrain_surface_height(point.x, point.y)) < 0.002)
	assert(verify_exclusions(), "Context exclusion checks failed")
	assert(await verify_buttons(preview), "UI interaction checks failed")
	print("PASS: mapped context (%s trees, %s roads, %s buildings), triangle grounding, forest pixels, site/road exclusions and button states" % [trees, context.get_meta("road_count"), context.get_meta("building_count")])
	quit()

func verify_exclusions() -> bool:
	var layout = {"perimeter": {"polygon": [[-25,-25], [25,-25], [25,25], [-25,25]]}, "terrain_grading": {"margin_m": 5}}
	var data = {"extent_m": 280, "roads": [
		{"points": [[-130,70], [130,70]], "width_m": 8},
		{"points": [[-10,0], [10,0]], "width_m": 4}],
		"buildings": [{"polygon": [[60,-90], [80,-90], [80,-70], [60,-70]], "height_m": 8},
		{"polygon": [[-5,-5], [5,-5], [5,5], [-5,5]], "height_m": 8}]}
	var cover = Image.create(8, 8, false, Image.FORMAT_RGBA8)
	cover.fill(Color("006400"))
	var height_at = func(x: float, z: float) -> float: return x * 0.05 + z * 0.02
	var context = Context.make(data, cover, height_at, layout)
	root.add_child(context)
	assert(context.get_meta("road_count") == 1 and context.get_meta("building_count") == 1)
	assert(context.get_meta("tree_count") > 100)
	for chunk in context.get_node("Forest").get_children():
		for index in range(chunk.multimesh.instance_count):
			var p: Vector3 = chunk.position + chunk.multimesh.get_instance_transform(index).origin
			assert(absf(p.y - height_at.call(p.x, p.z)) < 0.002)
			assert(absf(p.x) > 30 or absf(p.z) > 30, "No forest in the graded site")
			assert(absf(p.z - 70) >= 11 or absf(p.x) > 130, "No crowns in the road corridor")
			assert(p.x < 53 or p.x > 87 or p.z < -97 or p.z > -63, "No crowns in buildings")
	context.free()
	cover.fill(Color("f096ff"))
	context = Context.make({"extent_m": 280}, cover, height_at, layout)
	assert(context.get_meta("tree_count") == 0, "Cropland must not become forest")
	context.free()
	return true

func verify_buttons(preview: Node) -> bool:
	var button: Button = preview.follow_button
	var column = button.get_parent()
	var panel: PanelContainer = preview.ui_panel
	assert(panel.get_global_rect().end.y < 840, "Controls must fit above attribution")
	var normal = button.get_theme_stylebox("normal") as StyleBoxFlat
	for state in ["normal", "hover", "pressed", "disabled"]:
		var style = button.get_theme_stylebox(state) as StyleBoxFlat
		assert(style != null and style.bg_color.a > 0.9 and style.border_width_left >= 1)
		assert(style.content_margin_left >= 12 and style.content_margin_top >= 8)
		if state != "normal":
			assert(style.bg_color != normal.bg_color)
	var point = button.get_global_rect().get_center()
	Input.warp_mouse(point)
	await process_frame
	var motion = InputEventMouseMotion.new()
	motion.position = point
	Input.parse_input_event(motion)
	await process_frame
	assert(button.get_draw_mode() == BaseButton.DRAW_HOVER)
	var press = InputEventMouseButton.new()
	press.position = point
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	Input.parse_input_event(press)
	await process_frame
	assert(button.get_draw_mode() == BaseButton.DRAW_PRESSED)
	# Capture the real pressed control beside disabled scenario controls.
	for child in column.get_children():
		if child is HBoxContainer and child != preview.previous_drone_button.get_parent():
			for control in child.get_children():
				if control is Button:
					control.disabled = true
	await process_frame
	await RenderingServer.frame_post_draw
	assert(root.get_texture().get_image().save_png(ProjectSettings.globalize_path("res://../artifacts/korea-controls.png")) == OK)
	press.pressed = false
	Input.parse_input_event(press)
	await process_frame
	assert(preview.follow_drone, "Styled button must still receive clicks")
	button.disabled = true
	assert(button.get_draw_mode() == BaseButton.DRAW_DISABLED)
	var camera_before: Transform3D = preview.camera.transform
	var time_before: float = preview.elapsed_ms
	var selected_before: int = preview.selected_drone_index
	await click(preview.ui_toggle)
	assert(not preview.ui_body.visible and preview.ui_toggle.text == "+")
	assert(panel.size.y < 100 and panel.size.x < 260, "Collapsed panel must release the 3D viewport")
	assert(preview.camera.transform.is_equal_approx(camera_before) and preview.elapsed_ms == time_before)
	assert(preview.selected_drone_index == selected_before and preview.follow_drone)
	await RenderingServer.frame_post_draw
	assert(root.get_texture().get_image().save_png(ProjectSettings.globalize_path("res://../artifacts/korea-panel-collapsed.png")) == OK)
	await click(preview.ui_toggle)
	assert(preview.ui_body.visible and preview.ui_toggle.text == "−")
	assert(panel.size.y > 700 and panel.get_global_rect().end.y < 840)
	assert(preview.camera.transform.is_equal_approx(camera_before) and preview.elapsed_ms == time_before)
	# Repeating collapse/expand must neither grow the panel nor lose controls.
	await click(preview.ui_toggle)
	await click(preview.ui_toggle)
	assert(preview.ui_body.visible and preview.follow_button == button)
	root.size = Vector2i(1280, 720)
	for frame in range(4):
		await process_frame
	assert(panel.get_global_rect().end.y <= 650, "Short windows must keep controls above attribution")
	assert(preview.ui_scroll.get_v_scroll_bar().visible, "Long controls must remain accessible by scrolling")
	root.size = Vector2i(1440, 900)
	print("PASS: collapse/expand clicks preserve camera, follow target, replay time and control instances")
	return true

func click(button: Button) -> void:
	Input.warp_mouse(button.get_global_rect().get_center())
	await process_frame
	var motion = InputEventMouseMotion.new()
	motion.position = button.get_global_rect().get_center()
	Input.parse_input_event(motion)
	var event = InputEventMouseButton.new()
	event.position = button.get_global_rect().get_center()
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	Input.parse_input_event(event)
	await process_frame
	event.pressed = false
	Input.parse_input_event(event)
	await process_frame
	await process_frame
