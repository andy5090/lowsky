extends SceneTree
## Procedural display geometry, with no external models or textures.

var palette = {
	"ground": Color("344d49"), "edge": Color("21332f"), "asphalt": Color("253139"),
	"white": Color("e3e8de"), "body": Color("9babb4"), "dark": Color("354651"),
	"glass": Color("54acbb"), "accent": Color("ecb969"), "cyan": Color("73ded7")
}

func mesh_part(root: Node3D, part_name: String, mesh: Mesh, position: Vector3, color_name: String) -> MeshInstance3D:
	var part = MeshInstance3D.new()
	part.name = part_name
	part.mesh = mesh
	part.position = position
	var material = StandardMaterial3D.new()
	material.albedo_color = palette[color_name]
	material.roughness = 0.85
	part.material_override = material
	root.add_child(part)
	return part

func box(root: Node3D, part_name: String, size: Vector3, position: Vector3, color_name: String) -> MeshInstance3D:
	var mesh = BoxMesh.new()
	mesh.size = size
	return mesh_part(root, part_name, mesh, position, color_name)

func cylinder(root: Node3D, part_name: String, radius: float, height: float, position: Vector3, color_name: String) -> MeshInstance3D:
	var mesh = CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = 12
	return mesh_part(root, part_name, mesh, position, color_name)

func create_asset(id: String) -> Node3D:
	var root = Node3D.new()
	root.name = id
	match id:
		"ground_tile":
			box(root, "Ground", Vector3(100, 1, 100), Vector3(0, -0.5, 0), "ground")
			box(root, "Base", Vector3(101, 0.6, 101), Vector3(0, -1.3, 0), "edge")
		"runway":
			box(root, "Surface", Vector3(8, 0.16, 60), Vector3(0, 0.08, 0), "asphalt")
			for side in [-1, 1]:
				box(root, "Edge_%s" % side, Vector3(0.12, 0.02, 58), Vector3(side * 3.65, 0.17, 0), "white")
			for index in range(9):
				box(root, "Center_%s" % index, Vector3(0.16, 0.02, 2.2), Vector3(0, 0.17, -24 + index * 6), "white")
			for side in [-1, 1]:
				for index in range(6):
					box(root, "Threshold_%s_%s" % [side, index], Vector3(0.35, 0.02, 2.5), Vector3(-2.5 + index, 0.17, side * 27), "white")
		"hangar":
			box(root, "Body", Vector3(10, 5, 10), Vector3(0, 2.5, 0), "body")
			box(root, "Roof", Vector3(10.6, 0.5, 10.6), Vector3(0, 5.25, 0), "dark")
			box(root, "Door", Vector3(7.4, 3.8, 0.12), Vector3(0, 1.9, 5.08), "dark")
			for index in range(5):
				box(root, "DoorSlat_%s" % index, Vector3(7.3, 0.045, 0.14), Vector3(0, 0.5 + index * 0.65, 5.16), "body")
			box(root, "Sign", Vector3(2, 0.35, 0.1), Vector3(0, 4.5, 5.15), "accent")
		"control_tower":
			box(root, "Base", Vector3(5, 0.5, 5), Vector3(0, 0.25, 0), "dark")
			box(root, "Shaft", Vector3(2.7, 8, 2.7), Vector3(0, 4.5, 0), "body")
			box(root, "Deck", Vector3(5.5, 0.4, 5.5), Vector3(0, 8.5, 0), "dark")
			box(root, "Cabin", Vector3(4.8, 1.8, 4.8), Vector3(0, 9.5, 0), "glass")
			box(root, "Roof", Vector3(5.5, 0.35, 5.5), Vector3(0, 10.6, 0), "dark")
			cylinder(root, "Mast", 0.08, 2, Vector3(0, 11.7, 0), "white")
		"observation_station":
			cylinder(root, "Base", 1.2, 0.3, Vector3(0, 0.15, 0), "dark")
			cylinder(root, "Post", 0.16, 3, Vector3(0, 1.8, 0), "body")
			box(root, "Housing", Vector3(1.4, 0.7, 0.9), Vector3(0, 3.5, 0), "white")
			box(root, "Display", Vector3(0.95, 0.4, 0.08), Vector3(0, 3.5, 0.49), "cyan")
		"aerial_marker":
			box(root, "Body", Vector3(1.1, 0.4, 1.4), Vector3.ZERO, "white")
			box(root, "Top", Vector3(0.55, 0.15, 0.7), Vector3(0, 0.25, 0), "cyan")
			box(root, "ArmX", Vector3(3.2, 0.12, 0.22), Vector3.ZERO, "dark")
			box(root, "ArmZ", Vector3(0.22, 0.12, 3.2), Vector3.ZERO, "dark")
			for offset in [Vector3(1.5, 0, 0), Vector3(-1.5, 0, 0), Vector3(0, 0, 1.5), Vector3(0, 0, -1.5)]:
				cylinder(root, "Rotor_%s" % root.get_child_count(), 0.55, 0.08, offset, "accent")
		"utility_building":
			box(root, "Body", Vector3(6, 3, 8), Vector3(0, 1.5, 0), "body")
			box(root, "Roof", Vector3(6.4, 0.3, 8.4), Vector3(0, 3.15, 0), "dark")
			for index in range(3):
				box(root, "Window_%s" % index, Vector3(1.2, 0.8, 0.08), Vector3(-2 + index * 2, 1.8, 4.05), "glass")
	return root

func _initialize() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://assets"))
	var manifest = {"schema_version": "1.0", "origin": "Generated locally with Godot primitives; no external assets", "axes": "Y-up", "unit": "fictional_scene_unit", "assets": []}
	for id in ["ground_tile", "runway", "hangar", "control_tower", "observation_station", "aerial_marker", "utility_building"]:
		var asset = create_asset(id)
		var document = GLTFDocument.new()
		var state = GLTFState.new()
		var error = document.append_from_scene(asset, state)
		if error == OK:
			error = document.write_to_filesystem(state, "res://assets/%s.glb" % id)
		asset.free()
		if error != OK:
			push_error("Asset export failed: %s (%s)" % [id, error])
			quit(1)
			return
		manifest.assets.append({"asset_id": id, "path": "res://assets/%s.glb" % id, "pivot": "center" if id == "aerial_marker" else "ground", "collision": false, "animation": false, "textures": false})
	var file = FileAccess.open("res://assets/manifest.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(manifest, "\t") + "\n")
	print("Exported %s GLB assets" % manifest.assets.size())
	quit()
