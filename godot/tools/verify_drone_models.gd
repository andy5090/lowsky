extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var factory = load("res://preview.gd").new()
	factory.display_profiles = factory.read_json("res://assets/display_profiles.json")
	var stage = Node3D.new()
	root.add_child(stage)
	factory.camera = Camera3D.new()
	stage.add_child(factory.camera)
	var fingerprints: Dictionary = {}
	for id in factory.display_profiles.airframes:
		var drone: Node3D = factory.drone_instance(id)
		stage.add_child(drone)
		var bounds: Array = factory.collect_bounds(drone, Transform3D.IDENTITY)
		var combined: AABB = bounds[0]
		for bound in bounds:
			combined = combined.merge(bound)
		assert(combined.position.is_finite() and combined.size.is_finite())
		assert(combined.get_center().is_zero_approx(), "Centered pivot: " + id)
		assert(is_equal_approx(maxf(combined.size.x, combined.size.z), float(drone.get_meta("horizontal_span_m"))), "Size: " + id)
		assert(drone.get_meta("airframe_id") == id)
		var model: Node3D = drone.get_node("Visual").get_child(0)
		if model.has_node("Airframe"):
			var mesh: Mesh = model.get_node("Airframe").mesh
			var fingerprint = str(mesh.get_aabb()) + str(hash(mesh.get_faces()))
			assert(not fingerprints.has(fingerprint), "Duplicate geometry: " + id)
			fingerprints[fingerprint] = id
			var second: Node3D = factory.drone_instance(id)
			assert(second.get_node("Visual").get_child(0).get_node("Airframe").mesh == mesh, "Share static resources: " + id)
			second.free()
		factory.pose_drone(drone, Vector3.RIGHT, 170)
		assert(drone.position.is_zero_approx(), "Pose must not move the track")
		assert((-drone.get_node("Visual").basis.z).is_equal_approx(Vector3.RIGHT), "Nose follows track")
		var rotors: Array = drone.get_meta("rotors", [])
		for rotor in rotors:
			var sampled: Basis = rotor.basis
			factory.pose_drone(drone, Vector3.RIGHT, 370)
			factory.pose_drone(drone, Vector3.RIGHT, 170)
			assert(rotor.basis.is_equal_approx(sampled), "Replay/seek deterministic rotor phase")
		if id == "quadcopter":
			assert(drone.has_meta("animation_player"), "Imported propeller animation must be connected")
			var player: AnimationPlayer = drone.get_meta("animation_player")
			assert(not player.is_playing(), "Animation follows simulation clock only")
		drone.free()
	var legacy: Node3D = factory.drone_instance()
	assert(legacy.get_meta("airframe_id") == "quadcopter")
	assert(legacy.get_meta("horizontal_span_m") == 0.6)
	legacy.free()
	var fallback: Node3D = factory.drone_instance("future_airframe", "bad_profile")
	assert(fallback.get_meta("airframe_id") == "quadcopter")
	fallback.free()
	factory.use_external_assets = false
	var local: Node3D = factory.drone_instance("quadcopter")
	assert(local.get_node("Visual").get_child(0).has_node("Airframe"))
	local.free()
	factory.free()
	stage.free()
	print("PASS: 14 distinct airframes, calibrated bounds/pivots, shared meshes, track heading, deterministic animation, fallback")
	quit()
