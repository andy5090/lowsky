// Local X points east, Z points south. Small-area spherical approximation.
export const EARTH_RADIUS = 6378137;
export function localToGeo(x, z, origin) {
  const radians = Math.PI / 180;
  return [origin.lat - z / EARTH_RADIUS / radians,
    origin.lon + x / (EARTH_RADIUS * Math.cos(origin.lat * radians)) / radians];
}
export function mercator(lat, lon, zoom) {
  const n = 256 * 2 ** zoom;
  const sine = Math.sin(Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI / 180);
  return [(lon + 180) / 360 * n, (0.5 - Math.log((1 + sine) / (1 - sine)) / (4 * Math.PI)) * n];
}
export function unproject(x, y, zoom) {
  const n = 256 * 2 ** zoom;
  return [Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI, x / n * 360 - 180];
}
export function pixelsPerMeter(lat, zoom) {
  return 256 * 2 ** zoom / (2 * Math.PI * EARTH_RADIUS * Math.cos(lat * Math.PI / 180));
}
