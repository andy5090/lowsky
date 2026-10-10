extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var preview = (load("res://preview.tscn") as PackedScene).instantiate()
	root.add_child(preview)
	preview.playing = false
	preview.set_process(false)
	var clock_before: float = preview.elapsed_ms
	if "--desktop-test-http" in OS.get_cmdline_user_args():
		assert(preview.desktop_mode)
		var deadline = Time.get_ticks_msec() + 5000
		while preview.desktop_revision < 0 and Time.get_ticks_msec() < deadline:
			await create_timer(0.05).timeout
		assert(preview.desktop_state.available)
		var before: int = preview.desktop_revision
		preview.desktop_command("show_monitor")
		assert(await wait_revision(preview, before))
		assert(preview.desktop_state.view == "monitor")
		before = preview.desktop_revision
		preview.desktop_command("toggle_3d_fullscreen")
		assert(await wait_revision(preview, before))
		assert(preview.desktop_state.fullscreen)
		assert(preview.desktop_state.view == "3d", "Explicit 3D fullscreen ignores stale monitor focus")
		assert(preview.elapsed_ms == clock_before and not preview.playing)
		print("PASS: desktop HTTP polling and POST controls change window state without replay changes")
	else:
		assert(not preview.desktop_mode)
		assert(preview.desktop_poll_request == null and preview.desktop_monitor_button == null)
		preview.desktop_mode = true
		var column = VBoxContainer.new()
		root.add_child(column)
		preview.build_desktop_controls(column)
		var state = {"available":true, "view":"monitor", "fullscreen":false, "three_d_open":true, "pending":false, "error":null, "revision":0}
		var action: Dictionary = preview.apply_desktop_state(state)
		assert(not action.focus and action.fullscreen == null, "Initial monitor state must never change the native Godot window")
		assert(preview.apply_desktop_state(state).is_empty(), "Repeated polls never grab focus")
		state.view = "3d"
		state.fullscreen = true
		state.revision = 1
		action = preview.apply_desktop_state(state)
		assert(action.focus and action.fullscreen)
		assert(preview.apply_desktop_state(state).is_empty())
		state.revision = 0
		assert(preview.apply_desktop_state(state).is_empty(), "Delayed responses cannot roll back native state")
		state.revision = 2
		state.pending = true
		assert(preview.apply_desktop_state(state).is_empty())
		assert(preview.desktop_monitor_button.disabled and preview.desktop_fullscreen_button.disabled)
		state.revision = 3
		state.pending = false
		state.view = "monitor"
		state.fullscreen = false
		action = preview.apply_desktop_state(state)
		assert(not action.focus and action.fullscreen == null)
		assert(preview.desktop_state.fullscreen == false, "Desired fullscreen stays stored for the next 3D revision")
		state.revision = 4
		state.view = "3d"
		action = preview.apply_desktop_state(state)
		assert(action.focus and action.fullscreen == false, "Deferred mode applies only when returning to 3D")
		state.revision = 5
		state.error = "Native window unavailable"
		assert(preview.apply_desktop_state(state).is_empty())
		assert("Native window unavailable" in preview.desktop_status.text)
		state.revision = 6
		state.error = null
		state.available = false
		assert(preview.apply_desktop_state(state).is_empty())
		assert(preview.desktop_monitor_button.disabled)
		preview.receive_desktop_state(HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), PackedByteArray())
		assert("disconnected" in preview.desktop_status.text)
		preview.receive_desktop_state(HTTPRequest.RESULT_SUCCESS, 409, PackedStringArray(), "{}".to_utf8_buffer())
		assert("409" in preview.desktop_status.text)
		preview.receive_desktop_state(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), "{}".to_utf8_buffer())
		assert("Invalid" in preview.desktop_status.text)
		assert(preview.elapsed_ms == clock_before and not preview.playing)
		column.queue_free()
		print("PASS: desktop-only controls, revision/focus/fullscreen gates, unavailable/error handling; replay unchanged")
	preview.queue_free()
	await process_frame
	quit()

func wait_revision(preview, before: int) -> bool:
	var deadline = Time.get_ticks_msec() + 5000
	while preview.desktop_revision <= before and Time.get_ticks_msec() < deadline:
		await create_timer(0.05).timeout
	return preview.desktop_revision > before
