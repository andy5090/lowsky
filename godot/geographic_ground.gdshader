shader_type spatial;
render_mode diffuse_burley, specular_disabled;

uniform sampler2D satellite : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D grass_detail : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float extent_m = 10000.0;
varying vec2 ground_position;

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float noise2(vec2 p) {
	vec2 cell = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash21(cell), hash21(cell + vec2(1.0, 0.0)), f.x),
		mix(hash21(cell + vec2(0.0, 1.0)), hash21(cell + vec2(1.0)), f.x), f.y);
}

void vertex() {
	ground_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz;
}

void fragment() {
	vec2 p = ground_position;
	vec2 map_uv = p / extent_m + vec2(0.5);
	// The composite already contains illumination; lower reflectance under the HDR sky.
	vec3 mapped = texture(satellite, map_uv).rgb * 0.6;
	// Low-frequency variation breaks the old identical 20 m lawn pattern.
	float broad = noise2(p / 170.0) * 0.65 + noise2(p / 43.0) * 0.35;
	vec3 maintained = mix(vec3(0.19, 0.235, 0.13), vec3(0.32, 0.35, 0.21), broad);
	vec3 detail_a = texture(grass_detail, p * 0.17).rgb;
	vec2 rotated = mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * p;
	vec3 detail_b = texture(grass_detail, rotated * 0.113 + vec2(0.37, 0.61)).rgb;
	float grain = dot(mix(detail_a, detail_b, noise2(p / 29.0)), vec3(0.3333));
	float near_detail = 1.0 - smoothstep(100.0, 700.0, length(VERTEX));
	// COLOR.r only marks the fictional redeveloped site. Satellite is unique outside it.
	ALBEDO = mix(mapped, maintained, COLOR.r) * mix(1.0, 0.87 + grain * 0.35, near_detail);
	ROUGHNESS = 0.98;
	SPECULAR = 0.0;
}
