extends SceneTree
## Reproducible contact sheet of the actual runtime models, with independent framing.

func _initialize() -> void:
	call_deferred("capture")

func caption(parent: Node, text: String, position: Vector2, font_size: int, color: Color) -> void:
	var label = Label.new()
	label.text = text
	label.position = position
	label.add_theme_font_size_override("font_size", font_size)
	label.modulate = color
	parent.add_child(label)

func capture() -> void:
	root.size = Vector2i(1800, 1390)
	var factory = load("res://preview.gd").new()
	factory.display_profiles = factory.read_json("res://assets/display_profiles.json")
	var background = ColorRect.new()
	background.color = Color("111b23")
	background.size = Vector2(1800, 1390)
	root.add_child(background)
	caption(root, "LOW SKY  /  AIRFRAME STUDY", Vector2(36, 22), 30, Color("eef0ed"))
	caption(root, "14 visual variants · individually framed · provisional display dimensions", Vector2(36, 64), 17, Color("9cabb6"))
	var ids: Array = factory.display_profiles.airframes.keys()
	ids.append("blockout")
	for index in ids.size():
		var id: String = ids[index]
		var origin = Vector2(26 + (index % 4) * 444, 110 + (index / 4) * 303)
		var container = SubViewportContainer.new()
		container.position = origin
		root.add_child(container)
		var viewport = SubViewport.new()
		viewport.size = Vector2i(430, 250)
		viewport.own_world_3d = true
		viewport.msaa_3d = Viewport.MSAA_4X
		container.add_child(viewport)
		var stage = Node3D.new()
		viewport.add_child(stage)
		var environment = WorldEnvironment.new()
		environment.environment = Environment.new()
		environment.environment.background_mode = Environment.BG_COLOR
		environment.environment.background_color = Color("202d37")
		environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.environment.ambient_light_color = Color("b8c9df")
		environment.environment.ambient_light_energy = 0.65
		stage.add_child(environment)
		var sun = DirectionalLight3D.new()
		sun.rotation_degrees = Vector3(-45, -30, 0)
		sun.light_energy = 1.6
		stage.add_child(sun)
		factory.realistic = id != "blockout"
		var drone: Node3D = factory.drone_instance(id)
		stage.add_child(drone)
		var span = float(drone.get_meta("horizontal_span_m"))
		var camera = Camera3D.new()
		stage.add_child(camera)
		camera.position = Vector3(1.0, 0.95, -1.6) * span
		camera.near = 0.01
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = span * 1.35
		camera.look_at(Vector3.ZERO)
		var label = "Previous placeholder" if id == "blockout" else str(factory.display_profiles.airframes[id].label)
		caption(root, label, origin + Vector2(9, 254), 18, Color("edf0eb"))
		caption(root, "%s m display span" % span, origin + Vector2(9, 278), 14, Color("9cabb6"))
	caption(root, "Visual approximations, not verified replicas.\nCesiumDrone: Ed Mackey / AGI · CC BY 4.0\nOther models: locally generated geometry.", Vector2(1370, 1100), 16, Color("a7b6bf"))
	for frame in range(12):
		await process_frame
	await RenderingServer.frame_post_draw
	var path = ProjectSettings.globalize_path("res://../artifacts/drone-catalog.png")
	var error = root.get_texture().get_image().save_png(path)
	factory.free()
	print("Drone catalog saved: ", path)
	quit(error)
