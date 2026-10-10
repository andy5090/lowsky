#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs::{self, File},
    io::{BufRead, BufReader},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    Manager, WebviewUrl, WebviewWindowBuilder,
};

#[derive(Default)]
struct Processes {
    backend: Option<Child>,
    godot: Option<Child>,
    port: Option<u16>,
}
struct Runtime {
    processes: Mutex<Processes>,
    payload: PathBuf,
    data: PathBuf,
    stopped: AtomicBool,
}

fn quiet(command: &mut Command) -> &mut Command {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
}
fn terminate(child: &mut Child, graceful: bool) {
    drop(child.stdin.take());
    if graceful {
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            if matches!(child.try_wait(), Ok(Some(_))) {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
    }
    let _ = child.kill();
    let _ = child.wait();
}
impl Runtime {
    fn shutdown(&self) {
        self.stopped.store(true, Ordering::SeqCst);
        let mut processes = self.processes.lock().unwrap();
        if let Some(mut child) = processes.godot.take() {
            terminate(&mut child, false);
        }
        if let Some(mut child) = processes.backend.take() {
            terminate(&mut child, true);
        }
        processes.port = None;
    }
    fn start_backend(&self) -> Result<u16, String> {
        let executable = self.payload.join("backend").join(if cfg!(windows) {
            "lowsky-server.exe"
        } else {
            "lowsky-server"
        });
        let log = File::create(self.data.join("backend.log")).map_err(|e| e.to_string())?;
        let mut processes = self.processes.lock().unwrap();
        if self.stopped.load(Ordering::SeqCst) {
            return Err("Application is shutting down".into());
        }
        let mut child = quiet(
            Command::new(executable)
                .arg("--data-dir")
                .arg(&self.data)
                .arg("--port")
                .arg("0")
                .current_dir(&self.data)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(log),
        )
        .spawn()
        .map_err(|e| format!("Could not start the local service: {e}"))?;
        let stdout = child.stdout.take().ok_or("Missing startup channel")?;
        processes.backend = Some(child);
        drop(processes);
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut line = String::new();
            let result = reader
                .read_line(&mut line)
                .map(|_| line)
                .map_err(|e| e.to_string());
            let _ = sender.send(result);
            // Keep draining stdout so a child can never block on a full pipe.
            let _ = std::io::copy(&mut reader, &mut std::io::sink());
        });
        let result = receiver
            .recv_timeout(Duration::from_secs(45))
            .map_err(|_| "Local service startup timed out. See backend.log.".to_string())??;
        let ready: serde_json::Value =
            serde_json::from_str(&result).map_err(|_| "Invalid local service startup response")?;
        let port = ready["port"]
            .as_u64()
            .filter(|p| *p > 0 && *p <= u16::MAX as u64)
            .ok_or("Missing local service port")? as u16;
        if ready["event"] != "ready" {
            return Err("Local service did not become ready".into());
        }
        let mut processes = self.processes.lock().unwrap();
        if self.stopped.load(Ordering::SeqCst) {
            return Err("Application is shutting down".into());
        }
        processes.port = Some(port);
        Ok(port)
    }
    fn start_godot(&self) -> Result<(), String> {
        let mut processes = self.processes.lock().unwrap();
        if self.stopped.load(Ordering::SeqCst) {
            return Err("Application is shutting down".into());
        }
        if let Some(child) = processes.godot.as_mut() {
            if matches!(child.try_wait(), Ok(None)) {
                return Ok(());
            }
        }
        let port = processes.port.ok_or("Local service is not running yet")?;
        let relative = fs::read_to_string(self.payload.join("godot-executable.txt"))
            .map_err(|e| e.to_string())?;
        let relative = Path::new(relative.trim());
        if relative
            .components()
            .any(|part| !matches!(part, std::path::Component::Normal(_)))
        {
            return Err("Invalid packaged 3D executable path".into());
        }
        let executable = self.payload.join(relative);
        let log = File::create(self.data.join("godot.log")).map_err(|e| e.to_string())?;
        let stderr = log.try_clone().map_err(|e| e.to_string())?;
        let data_root = self.payload.join("backend/_internal/data");
        processes.godot = Some(
            quiet(
                Command::new(executable)
                    .arg("--")
                    .arg("--monitor")
                    .arg(format!("--monitor-port={port}"))
                    .arg(format!("--data-root={}", data_root.display()))
                    .current_dir(&self.data)
                    .stdin(Stdio::null())
                    .stdout(log)
                    .stderr(stderr),
            )
            .spawn()
            .map_err(|e| format!("Could not start 3D: {e}"))?,
        );
        Ok(())
    }
}
impl Drop for Runtime {
    fn drop(&mut self) {
        self.shutdown();
    }
}
fn show_error(app: &tauri::AppHandle, message: &str) {
    if let Some(window) = app.get_webview_window("launcher") {
        let text = serde_json::to_string(message).unwrap();
        let _ = window.eval(format!("document.getElementById('status').textContent={text};document.getElementById('help').textContent='Open LOW SKY → Application data for logs. Quit and reopen after correcting the problem.';"));
        let _ = window.show();
    }
    eprintln!("{message}");
}
fn open_path(path: &Path) {
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open").arg(path).spawn();
    }
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("explorer.exe").arg(path).spawn();
    }
}
fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let data = app.path().app_data_dir()?;
            fs::create_dir_all(&data)?;
            let config = data.join(".env");
            if !config.exists() {
                fs::write(&config, "# LOW SKY agent settings. Restart the app after editing.\n# Never share this file with your API key.\nOPENAI_API_KEY=\nLOW_SKY_AGENT_MODEL=openai:gpt-6.1-sol\n")?;
                #[cfg(unix)] { use std::os::unix::fs::PermissionsExt; fs::set_permissions(&config, fs::Permissions::from_mode(0o600))?; }
            }
            app.manage(Runtime { processes: Mutex::new(Processes::default()), payload: app.path().resource_dir()?.join("payload"), data, stopped: AtomicBool::new(false) });
            let view = MenuItem::with_id(app, "3d", "Open 3D simulation / 3D 열기", true, None::<&str>)?;
            let settings = MenuItem::with_id(app, "data", "Application data & agent settings…", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[
                &Submenu::with_items(app, "LOW SKY", true, &[&view, &settings, &PredefinedMenuItem::separator(app)?, &PredefinedMenuItem::quit(app, None)?])?,
                &Submenu::with_items(app, "Edit", true, &[&PredefinedMenuItem::copy(app, None)?, &PredefinedMenuItem::paste(app, None)?, &PredefinedMenuItem::select_all(app, None)?])?,
            ])?;
            app.set_menu(menu)?;
            let handle = app.handle().clone();
            thread::spawn(move || {
                let runtime = handle.state::<Runtime>();
                let result = (|| -> Result<(), String> {
                    let port = runtime.start_backend()?;
                    let url: tauri::Url = format!("http://127.0.0.1:{port}").parse().unwrap();
                    let allowed = url.clone();
                    WebviewWindowBuilder::new(&handle, "monitor", WebviewUrl::External(url))
                        .title("LOW SKY · Decision workspace").inner_size(1440.0, 960.0).min_inner_size(800.0, 600.0)
                        .on_navigation(move |url| url.scheme() == allowed.scheme() && url.host_str() == allowed.host_str() && url.port() == allowed.port())
                        .build().map_err(|e| e.to_string())?;
                    runtime.start_godot()?;
                    if let Some(window) = handle.get_webview_window("launcher") { let _ = window.close(); }
                    Ok(())
                })();
                if let Err(error) = result { runtime.shutdown(); show_error(&handle, &error); }
            });
            Ok(())
        })
        .on_menu_event(|app, event| {
            let runtime = app.state::<Runtime>();
            match event.id().as_ref() {
                "3d" => { if let Err(error) = runtime.start_godot() { show_error(app, &error); } },
                "data" => open_path(&runtime.data),
                _ => {}
            }
        })
        .build(tauri::generate_context!()).expect("Unable to initialize LOW SKY desktop");
    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            app.state::<Runtime>().shutdown();
        }
    });
}
