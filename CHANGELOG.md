# Changelog

All notable changes to LOW SKY are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the version is below 1.0.0, a minor bump (0.x.0) marks new features or changed behaviour and a patch bump (0.x.y) marks fixes only.

Update the `Unreleased` section in the same change as the code. To release, run `tools/bump_version.py <version>`: it moves `Unreleased` under the new version and date and updates every version field used by the installers. Planned work lives in [ROADMAP.md](ROADMAP.md).

## [Unreleased]

## [0.2.0] - 2026-10-11

### Added
- Dedicated LOW SKY 3D View app icon for macOS and Windows, and a LOW SKY start-up screen in place of the Godot engine logo.
- 3D view panel header with the LOW SKY shield logo and the "LOW SKY 3D" title in the monitor's brand typeface.
- The 3D view follows the language selected in the monitoring app (English or Korean).
- Installer builds can also copy the finished installer to a configured folder, such as a synced Google Drive folder.
- The AI settings dialog shows the app version.
- This changelog, a roadmap, and a version bump script with a consistency test.

### Fixed
- The collapsed 3D control panel now shrinks to its title row instead of keeping its full width.

## [0.1.0] - 2026-10-11

First installable version (macOS DMG and Windows NSIS from `desktop/build.py`).

### Added
- Virtual airfield site, northern Gyeonggi terrain and three scenario cases (48, 96 and 240 objects) with received observations, briefings and evaluation checkpoints.
- Bilingual (English/Korean) observation monitor with a shared simulation clock, received-evidence track review, current alerts, PWA notifications and severity-based alert sounds.
- Community early signals with a replay-synchronized radar overlay, and drone acoustic listening posts.
- Situation assessments and event-driven decision checkpoints through a Deep Agents runtime, with explicit human confirmation, deadlines, rehearsal reviews and durable decision journals.
- Per-user AI settings: choose OpenAI or Claude, enter your own API key in the app, and load the models each key can use.
- Tactics training layer: target identification, weapon and response recommendations, formation, and placement optimization for infantry, radars, acoustic listening posts and effector teams.
- Radar placement by terrain line-of-sight with additional radars and repositioning proposals that require confirmation.
- Enemy drones launch north of the Military Demarcation Line (Natural Earth MDL with nominal DMZ limits) and approach along varied curved corridors.
- Godot 3D view with mapped Korean surroundings, a drone airframe catalog, follow and approach cameras, and fullscreen and window switching.
- Native desktop package that bundles the monitor, local Python runtime, Godot 3D app and datasets in one installer.
- Instructor scene control kept separate from trainee decisions.

### Fixed
- Removed nested double scrolling across the workspace.
- OpenAI model list now shows current models available to the entered key.

[Unreleased]: https://github.com/andy5090/lowsky/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/andy5090/lowsky/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/andy5090/lowsky/releases/tag/v0.1.0
