use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, RunEvent, Url, WindowEvent};
use tauri_plugin_deep_link::DeepLinkExt;
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
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

/// Extract a .ace file path from a list of URL strings (macOS deep-link)
/// or plain path strings (Windows/Linux argv).
fn extract_ace_path(items: &[String]) -> Option<String> {
    for item in items {
        // Common case: plain filesystem path (Windows/Linux argv, macOS argv).
        // Checked first to avoid Url::parse succeeding on Windows drive letters
        // (e.g. "C:\path" parses with scheme "c").
        if std::path::Path::new(item)
            .extension()
            .and_then(|e| e.to_str())
            == Some("ace")
        {
            return Some(item.clone());
        }
        // macOS deep-link delivers file:// URLs
        if let Ok(url) = Url::parse(item) {
            if url.scheme() == "file" {
                if let Ok(path) = url.to_file_path() {
                    if path.extension().and_then(|e| e.to_str()) == Some("ace") {
                        return Some(path.to_string_lossy().into_owned());
                    }
                }
            }
        }
    }
    None
}

/// Navigate the webview to the coding page, optionally opening a project first.
fn open_ace_file(app: &AppHandle, path: &str, confirm: bool) {
    let filename = std::path::Path::new(path)
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| path.to_string());

    if confirm {
        let confirmed = app
            .dialog()
            .message(format!(
                "Open {}?\nThis will close the current project.",
                filename
            ))
            .title("Open Project")
            .kind(MessageDialogKind::Info)
            .buttons(MessageDialogButtons::OkCancel)
            .blocking_show();

        if !confirmed {
            // Just focus the window
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
            }
            return;
        }
    }

    if let Some(window) = app.get_webview_window("main") {
        let encoded = urlencoding::encode(path);
        let url = format!("http://127.0.0.1:{PORT}/code?open={encoded}");
        if let Ok(parsed) = Url::parse(&url) {
            let _ = window.navigate(parsed);
            let _ = window.set_focus();
        }
    }
}

fn main() {
    let child: Arc<Mutex<Option<CommandChild>>> = Arc::new(Mutex::new(None));
    let child_clone = child.clone();

    // Collect any .ace path from command-line args (Windows/Linux cold start).
    // Skip argv[0] (the executable path itself).
    let startup_path: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(
        extract_ace_path(
            &std::env::args().skip(1).collect::<Vec<_>>(),
        ),
    ));
    let startup_path_clone = startup_path.clone();

    let app = tauri::Builder::default()
        // Plugin order matters: single-instance BEFORE deep-link (per Tauri docs)
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            // Already running — file path arrives as argv on Windows/Linux
            if let Some(path) = extract_ace_path(&args) {
                open_ace_file(app, &path, true);
            } else if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
            let window = app.get_webview_window("main")
                .expect("main window not found");

            // macOS: check if launched via file association (cold start)
            if let Ok(Some(urls)) = app.deep_link().get_current() {
                let url_strings: Vec<String> =
                    urls.iter().map(|u| u.to_string()).collect();
                if let Some(path) = extract_ace_path(&url_strings) {
                    if let Ok(mut guard) = startup_path_clone.lock() {
                        *guard = Some(path);
                    }
                }
            }

            // macOS: listen for file-open events while running
            let app_handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                let url_strings: Vec<String> =
                    event.urls().iter().map(|u| u.to_string()).collect();
                if let Some(path) = extract_ace_path(&url_strings) {
                    open_ace_file(&app_handle, &path, true);
                }
            });

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

            let startup_path_thread = startup_path.clone();
            std::thread::spawn(move || {
                if wait_for_server(PORT, STARTUP_TIMEOUT) {
                    let file_path = startup_path_thread
                        .lock()
                        .ok()
                        .and_then(|mut g| g.take());

                    let target = if let Some(ref path) = file_path {
                        let encoded = urlencoding::encode(path);
                        format!("http://127.0.0.1:{PORT}/code?open={encoded}")
                    } else {
                        format!("http://127.0.0.1:{PORT}")
                    };

                    let url = Url::parse(&target).expect("invalid server URL");
                    let _ = window.navigate(url);
                    std::thread::sleep(Duration::from_millis(300));
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
