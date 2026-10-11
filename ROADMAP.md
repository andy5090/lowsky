# Roadmap

Planned work for LOW SKY, grouped by target version. Items move to [CHANGELOG.md](CHANGELOG.md) when they ship. Order within a version is priority order. Dates are not committed; the version number is the plan.

The project boundaries in [docs/mvp-direction.md](docs/mvp-direction.md) still apply. Advice uses received evidence only, there is no engagement or damage model, and every decision needs human confirmation. Items that would cross those boundaries need a separate scope decision first.

## 0.3.0 - Distribution and polish

- **Windows installer parity:** build and smoke-test the Windows NSIS installer on Windows, and configure rcedit so the 3D View executable carries the LOW SKY 3D icon in Explorer.
- **Signed releases:** Apple Developer signing and notarization for macOS, and a Windows code-signing certificate, so Gatekeeper and SmartScreen do not warn.
- **In-app version display:** show the app version in the monitor and the 3D view, and link it to this changelog.
- **Release automation:** one command that bumps the version, builds, smoke-tests, copies the installer to the shared folder and tags the release.

## 0.4.0 - Scenario depth

- **Drone role and link data:** apply scenario roles, link medium and link state from [docs/drone-scenario-extension.md](docs/drone-scenario-extension.md) to the run data and the communication simulation.
- **Radar realism options:** optional clutter and propagation assumptions on top of the current terrain line-of-sight model, clearly labelled as training assumptions.
- **More focused scenarios:** add cases only where they test a new decision, keeping the small focused set preferred over a large generated set.

## 0.5.0 - Review and evaluation

- **Agent configuration comparison:** run the single-agent and role-split configurations on fixed inputs and compare results, review measures and usage on one screen, as planned in the MVP direction.
- **Seven-field review records:** store human reviews with the seven fields from the MVP direction and replay them with the original event and explanation.

## Later, needs a separate scope decision

- **Site replacement:** switch the site layout, terrain, georeferencing and assets together from one definition instead of several coordinated files.
- **SAPIENT compatibility:** a versioned adapter with official schema validation and interoperability tests before any compatibility claim.
- **Field infrastructure:** IoT eSIM sensor nodes, external institutional routing and deployment at a real airfield remain proposals.
