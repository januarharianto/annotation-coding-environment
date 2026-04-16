use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const PORT: u16 = 18080;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(15);

fn wait_for_server(port: u16, timeout: Duration) -> bool {
    let addr = format!("127.0.0.1:{port}");
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect_timeout(
            &addr.parse().unwrap(),
            Duration::from_millis(200),
        )
        .is_ok()
        {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

fn main() {
    let child: Arc<Mutex<Option<CommandChild>>> = Arc::new(Mutex::new(None));
    let child_clone = child.clone();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
            }
        }))
        .setup(move |app| {
            let window = app.get_webview_window("main")
                .expect("main window not found");

            // Dev mode: server already running externally, just show window
            if cfg!(debug_assertions) {
                let _ = window.show();
                return Ok(());
            }

            // Production: spawn sidecar
            let sidecar = app.shell()
                .sidecar("ace-server")
                .expect("sidecar binary 'ace-server' not found in binaries/")
                .args(["--port", &PORT.to_string()]);
            let (_rx, sidecar_child) = sidecar
                .spawn()
                .expect("failed to start ACE server");

            *child_clone.lock().unwrap() = Some(sidecar_child);

            // Wait for server on a background thread (do NOT block main thread)
            std::thread::spawn(move || {
                if wait_for_server(PORT, STARTUP_TIMEOUT) {
                    let _ = window.set_title("ACE");
                    let _ = window.show();
                } else {
                    eprintln!("ACE server failed to start within timeout");
                    std::process::exit(1);
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri app");

    // Kill the sidecar on every quit path — RunEvent::Exit alone is
    // unreliable on macOS (Cmd+Q, dock quit, window close).  Calling kill
    // multiple times is safe: after the first .take() the Mutex holds None.
    let child_exit = child.clone();
    app.run(move |_app, event| {
        match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                kill_sidecar(&child_exit);
            }
            RunEvent::WindowEvent {
                event: WindowEvent::CloseRequested { .. },
                ..
            } => {
                kill_sidecar(&child_exit);
            }
            _ => {}
        }
    });
}

fn kill_sidecar(child: &Arc<Mutex<Option<CommandChild>>>) {
    if let Ok(mut guard) = child.lock() {
        if let Some(c) = guard.take() {
            let _ = c.kill();
        }
    }
}
