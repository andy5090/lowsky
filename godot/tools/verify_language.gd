extends SceneTree
## The 3D view follows the monitor language published through /api/ui-language.
## Run against a server with `-- --monitor --monitor-port=PORT`; add --capture-language
## in a windowed run to save .local/lang-{ko,en}.png and lang-{ko,en}-bottom.png.

const UIText = preload("res://ui_text.gd")

var base_url = "http://127.0.0.1:8765"
var hangul = RegEx.create_from_string("[가-힣]")
## Latin text, " / ", then Hangul: the old "English / 한국어" double.
var bilingual = RegEx.create_from_string("[A-Za-z)] / [가-힣]")

func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--monitor-port="):
			base_url = "http://127.0.0.1:" + argument.trim_prefix("--monitor-port=")
	call_deferred("verify")

func publish(language: String) -> void:
	var request = HTTPRequest.new()
	root.add_child(request)
	request.timeout = 2
	assert(request.request(base_url + "/api/ui-language", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify({"language": language})) == OK)
	var response = await request.request_completed
	request.queue_free()
	assert(response[0] == HTTPRequest.RESULT_SUCCESS and response[1] == 200, "POST /api/ui-language failed")

func panel_texts(preview: Node3D) -> Array:
	var texts: Array = []
	for control in preview.ui_body.find_children("*", "Control", true, false):
		if (control is Button or control is Label) and control.is_visible_in_tree() and not control.text.is_empty():
			texts.append(control.text)
	return texts

func capture(preview: Node3D, language: String) -> void:
	if DisplayServer.get_name() == "headless" or not "--capture-language" in OS.get_cmdline_user_args():
		return
	for frame in range(10):
		await process_frame
	await RenderingServer.frame_post_draw
	for suffix in ["", "-bottom"]:
		if suffix != "":
			# Second capture shows the long hint text at the end of the scrolled panel.
			preview.ui_scroll.scroll_vertical = 100000
			for frame in range(5):
				await process_frame
			await RenderingServer.frame_post_draw
		var path = ProjectSettings.globalize_path("res://../.local/lang-%s%s.png" % [language, suffix])
		assert(root.get_texture().get_image().save_png(path) == OK)
		print("Captured " + path)
	preview.ui_scroll.scroll_vertical = 0

func verify() -> void:
	await publish("en")
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	await create_timer(0.8).timeout
	assert(preview.monitor_mode and preview.monitor_connected)
	assert(UIText.language == "en")
	for text in panel_texts(preview):
		assert(hangul.search(text) == null, "English panel has no Korean: " + text)
	assert(preview.follow_button.text == "Follow selected drone  [F]")
	assert(preview.ui_title.text == "LOW SKY 3D")
	await capture(preview, "en")

	await publish("ko")
	await create_timer(0.6).timeout
	assert(UIText.language == "ko", "Godot follows the monitor language")
	var buttons = preview.ui_body.find_children("*", "Button", true, false)
	assert(buttons.size() >= 8)
	for button in buttons:
		assert(hangul.search(button.text) != null, "Korean button: " + button.text)
		assert(bilingual.search(button.text) == null, "No bilingual double: " + button.text)
	for text in panel_texts(preview):
		assert(bilingual.search(text) == null, "No bilingual double: " + text)
	assert(preview.follow_button.text == "선택 드론 추적  [F]")
	assert(preview.status_label.text.begins_with("모니터링"))
	assert(preview.ui_toggle.tooltip_text == "패널 접기")
	assert(preview.ui_title.text == "LOW SKY 3D", "Title is shared by both languages")
	for label in preview.geography.line_labels:
		assert(hangul.search(label.text) != null and not "DMZ" in label.text and not "MDL" in label.text)
	preview.set_drone_positions(true)
	assert(preview.objects[0].label.text.begins_with("가상 "))
	for marker in preview.geography.launch_root.get_children():
		assert(marker.get_node("Label").text.begins_with("발진 구역\n· "))
	preview.set_drone_positions(false)
	await capture(preview, "ko")

	await publish("en")
	await create_timer(0.6).timeout
	assert(UIText.language == "en")
	for text in panel_texts(preview):
		assert(hangul.search(text) == null, "English restored: " + text)
	assert(preview.follow_button.text == "Follow selected drone  [F]")
	assert(preview.geography.line_labels[0].text == "MDL")
	print("PASS: 3D view follows /api/ui-language en -> ko -> en; single-language panel, world labels and title")
	quit()
