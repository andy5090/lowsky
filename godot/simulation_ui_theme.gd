extends RefCounted
## Explicit controls for the 3D panel; shared by normal, hover, pressed and keyboard states.

static func button_style(fill: Color, border: Color) -> StyleBoxFlat:
	var style = StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(5)
	style.content_margin_left = 14
	style.content_margin_right = 14
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	return style

static func make() -> Theme:
	var theme = Theme.new()
	theme.set_stylebox("normal", "Button", button_style(Color("243642"), Color("637b8b")))
	theme.set_stylebox("hover", "Button", button_style(Color("344e60"), Color("a5d9ed")))
	theme.set_stylebox("pressed", "Button", button_style(Color("174d59"), Color("7cdecf")))
	theme.set_stylebox("disabled", "Button", button_style(Color("1b252d"), Color("394751")))
	var focus = button_style(Color.TRANSPARENT, Color("b5efdf"))
	focus.draw_center = false
	focus.set_border_width_all(2)
	theme.set_stylebox("focus", "Button", focus)
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		theme.set_color(state, "Button", Color("f1f6f8"))
	theme.set_color("font_disabled_color", "Button", Color("7b8c97"))
	theme.set_font_size("font_size", "Button", 15)
	return theme
