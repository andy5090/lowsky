# LOW SKY desktop distribution

A single native installer contains the Tauri monitoring app, the Python/Deep Agents service, the exported Godot 3D application, and runtime datasets. End users do not need Node.js, Rust, Python, or the Godot editor. Launching LOW SKY opens the monitoring and 3D windows against one private loopback simulation clock. Closing the desktop application stops its child processes. Closing just 3D leaves monitoring running; reopen or activate it with **Open 3D** in the monitor toolbar or **LOW SKY → Open 3D simulation**. **Close 3D** closes only the 3D process. **F6** switches from monitoring to 3D, and from 3D back to monitoring; **F11** toggles fullscreen for the current workspace. The 3D toolbar also has **Monitoring** and **Fullscreen** buttons. Both views share the fullscreen setting and simulation clock. Switching windows does not pause time; reopening 3D reconnects to the current run. These controls appear only in the desktop app; standalone browser monitoring keeps its normal browser controls. macOS may animate between fullscreen Spaces.

The two windows are intentionally separate native surfaces. Godot is not embedded into the system webview: native-window embedding is platform-specific, while exporting 3D to WebAssembly would change the render/runtime environment. Both surfaces are installed and managed as one application.

## Install

- macOS: open the `.dmg`, then drag **LOW SKY.app** into Applications. The local build targets the Mac's CPU architecture; Godot is universal. macOS 12 or later.
- Windows: run the `-setup.exe` NSIS installer. It installs for the current user without requiring admin rights. The bundled WebView2 bootstrapper installs the system webview if missing (requires Internet on first setup). Windows 10/11 x64.
- Current packages use ad-hoc macOS signing and unsigned Windows executables. Public distribution with a verified publisher requires your Apple Developer signing/notarization credentials and a Windows code-signing certificate. These credentials are not committed. This project does not disable Gatekeeper or SmartScreen.

## Settings and user data

Choose **LOW SKY → AI model & API key… / AI 설정**, or **AI settings** in the monitor header, to pick OpenAI, Anthropic Claude or the offline rules-only overview, select a model, paste your own API key, test the connection and save. No restart is needed. Each user supplies their own key and is billed by their provider. Without a key, the app still simulates and shows how to configure the agent. Deep Agents and both provider SDKs are bundled; provider access needs Internet and your account.

Choose **LOW SKY → Application data folder…** to open the per-user folder:

- macOS: `~/Library/Application Support/com.lowsky.desktop/`
- Windows: `%APPDATA%\com.lowsky.desktop\`

It contains `agent-settings.json` (saved provider, models and keys, owner-only permissions), `.env`, `backend.log`, `godot.log` and the audit journals. The key is never shown again in the app; remove it with **Remove saved key** or by deleting `agent-settings.json`. The hidden `.env` remains an optional fallback for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and `LOW_SKY_AGENT_MODEL` (restart after editing); values saved in the dialog take priority.

The repository `.env`, source documents, `.local/`, and existing review journals are never included. Journals are written outside the install folder and survive application upgrades. The optional Codex virtual operator still requires a separately installed and authenticated Codex CLI; it is not part of this installer. Browser PWA installation and browser notifications depend on browser APIs and may be unavailable in the system webview; simulation and in-app alert UI remain available.

The backend chooses an unused `127.0.0.1` port and reports it directly to the launcher. It never attaches to an unrelated server already using port 8765. The remote monitoring page gets no Tauri IPC capabilities. It can request only the fixed window actions through the local service. The launcher acknowledges them with a per-process private token; no arbitrary commands or files can be executed. The packaged service exits on launcher stdin EOF, including launcher failure; normal desktop exit also closes 3D.

## Build on the target operating system

Install Node.js 24, Rust 1.92+, the native [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/), and Python 3.12. On macOS, Xcode Command Line Tools are sufficient; on Windows, install MSVC C++ Build Tools.

```sh
python -m venv .local/desktop-venv
# macOS: .local/desktop-venv/bin/python
# Windows: .local/desktop-venv/Scripts/python.exe
python -m pip install -r requirements-agent.txt -r requirements-desktop.txt
python desktop/build.py
```

Use the virtual environment's Python for both commands (or activate it first). The build script installs pinned Node dependencies, freezes the backend, downloads checksum-pinned Godot 4.5 templates/editor when needed, exports 3D, and runs Tauri bundling with the checked-in native icons. The first Godot template download is approximately 1.36 GB; subsequent builds reuse the verified local cache. To use an existing editor and installed templates, pass `--godot /path/to/Godot`.

Outputs are copied to `dist/` with `.sha256` checksum files. Unpacked resources live in ignored `desktop/src-tauri/payload/`. Runtime assets are copied from `data/` and `monitor/` only; the Python freezer includes only imported modules/dependencies.

```sh
python desktop/smoke.py --payload desktop/src-tauri/payload --check-sdk
python -m unittest tests.test_desktop_runtime tests.test_desktop_packaging -v
cd desktop
npm ci
cargo test --manifest-path src-tauri/Cargo.toml
```

The smoke check runs outside the repository with a temporary user folder, tests case/clock changes and served assets, launches exported 3D headlessly, and verifies backend shutdown. `--check-sdk` also exercises Deep Agents, its evidence tools, and structured output against a dummy OpenAI endpoint on loopback; it makes no external provider calls and needs no API key. `--skip-godot` isolates backend checks. After changing Python/frontend files, rebuild the backend; after changing Godot files, re-export 3D. `--skip-backend` and `--skip-godot` are local incremental-build options, not release defaults.

## Local distribution

Installer builds run locally on the target operating system. This public repository has no GitHub Actions packaging workflow, tag-triggered builds, artifact uploads, automatic releases or update feed. Build on a Mac for macOS and a Windows PC for Windows; this Python/Godot/Tauri bundle does not support cross-building the Windows installer on macOS. Keep installers in the ignored `dist/` directory and distribute them explicitly when needed.

To also place each finished installer in a shared folder, such as a folder synced by Google Drive for desktop, give the folder with `--publish-dir`, the `LOWSKY_INSTALLER_DIR` environment variable, or one line in the ignored `.local/installer-publish-dir.txt` (in that order of precedence). The build copies the installer under a temporary name, checks its hash and then replaces any earlier copy with the same name, so a sync client never uploads a half-written file. The folder path stays out of Git. A missing folder stops the build after `dist/` is written.

## Versions and releases

The installer version comes from `src-tauri/tauri.conf.json`. Record user-visible changes under `Unreleased` in the root [CHANGELOG.md](../CHANGELOG.md) together with the code, and keep planned work in [ROADMAP.md](../ROADMAP.md). To release, run `python tools/bump_version.py X.Y.Z`; it dates the `Unreleased` entries under the new version and updates the Tauri, npm, Cargo and Godot export version fields and the version shown at the top of both READMEs. `python tools/bump_version.py --check` and `tests/test_versioning.py` fail if any field disagrees with the latest changelog release. Commit, then tag the commit `vX.Y.Z`. A new version produces a new installer file name, so earlier installers in the shared folder stay available.


Packaging follows the official [Tauri resource bundling](https://v2.tauri.app/develop/resources/), [Windows installer](https://v2.tauri.app/distribute/windows-installer/), and [Godot 4.5 export](https://docs.godotengine.org/en/4.5/tutorials/export/exporting_projects.html) documentation.
