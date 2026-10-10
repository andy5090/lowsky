extends Control
## Received detection labels; optional SIM markers expose author positions.

var camera: Camera3D
var objects: Array = []
var followed_object_id = ""

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func _process(_delta: float) -> void:
	queue_redraw()

func markers() -> Array:
	var result: Array = []
	if not is_instance_valid(camera):
		return result
	for item in objects:
		if not item.label.visible:
			continue
		var target: Node3D = item.node
		if not is_instance_valid(target) or camera.is_position_behind(target.global_position):
			continue
		var anchor = target.global_position
		if item.object_id == followed_object_id:
			anchor += Vector3.UP * float(target.get_meta("horizontal_span_m", 0.6)) * 0.45
		var point = camera.unproject_position(anchor)
		if Rect2(Vector2.ZERO, get_viewport_rect().size).has_point(point):
			result.append({"point": point, "id": item.object_id, "sim": item.sim, "note": "" if item.sim else str(item.get("note", ""))})
	return result

func _draw() -> void:
	var font = ThemeDB.fallback_font
	var labels: Array[Rect2] = []
	var visible_markers = markers()
	for marker in visible_markers:
		var color = Color("edb0fb") if marker.sim else Color("78e4d2")
		var point: Vector2 = marker.point
		var radius = 6.0 if visible_markers.size() > 8 else 9.0
		draw_circle(point, radius, Color(0.06, 0.03, 0.08, 0.85))
		draw_arc(point, radius, 0, TAU, 24, color, 2, true)
		draw_circle(point, 2, color)
		if visible_markers.size() > 8 and marker.id != visible_markers[0].id:
			continue
		var note: String = marker.note
		var width = 180.0
		if note != "":
			width = maxf(width, font.get_string_size(note, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 12.0)
		var box = Rect2(point + Vector2(15, -26), Vector2(width, 24 if note == "" else 42))
		for occupied in labels:
			if box.intersects(occupied.grow(3)):
				box.position.y = occupied.end.y + 4
		labels.append(box)
		draw_line(point + Vector2(10, 0), box.position + Vector2(0, 12), color, 1, true)
		draw_rect(box, Color(0.04, 0.06, 0.08, 0.92))
		draw_string(font, box.position + Vector2(6, 17), ("SIM " if marker.sim else "DETECTED ") + marker.id, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, color)
		if note != "":
			# Rule-based training advice from the shared state; the overlay only repeats the received-only label line.
			draw_string(font, box.position + Vector2(6, 35), note, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, color.darkened(0.15))
