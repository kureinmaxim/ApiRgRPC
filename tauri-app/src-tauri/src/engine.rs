//! Reticulum engine (sidecar) manager.
//!
//! Mirrors how ApiNgRPC drives `sing-box`: we spawn an external process
//! (`rns-engine`), keep its stdin to send line-delimited JSON commands, and
//! read its stdout on a background thread, forwarding each JSON line to the
//! frontend as a Tauri `rns-event`.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};

use tauri::{AppHandle, Emitter, Manager};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Default)]
pub struct Engine {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
}

impl Engine {
    pub fn is_running(&self) -> bool {
        self.child.is_some()
    }

    /// Build the command that launches the sidecar.
    /// Release: a bundled `rns-engine(.exe)` resource. Dev: `python` + script.
    fn build_command(app: &AppHandle) -> Result<Command, String> {
        let exe_name = if cfg!(windows) { "rns-engine.exe" } else { "rns-engine" };

        // 1) Bundled binary next to resources (production).
        if let Ok(res_dir) = app.path().resource_dir() {
            let bundled = res_dir.join(exe_name);
            if bundled.exists() {
                return Ok(Command::new(bundled));
            }
        }

        // 2) Dev fallback: run the Python script directly.
        // src-tauri/ -> ../../rns-engine/rns_engine.py
        let script = std::env::current_dir()
            .map(|d| d.join("../rns-engine/rns_engine.py"))
            .map_err(|e| e.to_string())?;
        let script = if script.exists() {
            script
        } else {
            // also try relative to the manifest dir during `tauri dev`
            std::path::PathBuf::from("../../rns-engine/rns_engine.py")
        };
        let mut cmd = Command::new(if cfg!(windows) { "python" } else { "python3" });
        cmd.arg(script);
        Ok(cmd)
    }

    pub fn start(&mut self, app: &AppHandle, display_name: &str) -> Result<(), String> {
        if self.is_running() {
            return Ok(());
        }

        let data_dir = app
            .path()
            .app_data_dir()
            .map_err(|e| format!("no app data dir: {e}"))?;
        let store = data_dir.join("store");
        let config = data_dir.join("reticulum");
        std::fs::create_dir_all(&store).ok();
        std::fs::create_dir_all(&config).ok();

        let mut cmd = Self::build_command(app)?;
        cmd.arg("--store").arg(&store)
            .arg("--config").arg(&config)
            .arg("--name").arg(display_name)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = cmd.spawn().map_err(|e| format!("failed to spawn engine: {e}"))?;

        let stdout = child.stdout.take().ok_or("no stdout")?;
        let stderr = child.stderr.take().ok_or("no stderr")?;
        self.stdin = child.stdin.take();
        self.child = Some(child);

        // Forward engine stdout JSON lines to the frontend.
        let app_out = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                let line = line.trim().to_string();
                if line.is_empty() {
                    continue;
                }
                match serde_json::from_str::<serde_json::Value>(&line) {
                    Ok(val) => {
                        let _ = app_out.emit("rns-event", val);
                    }
                    Err(_) => {
                        let _ = app_out.emit(
                            "rns-event",
                            serde_json::json!({"event":"log","level":"info","message": line}),
                        );
                    }
                }
            }
            let _ = app_out.emit(
                "rns-event",
                serde_json::json!({"event":"log","level":"warn","message":"engine stdout closed"}),
            );
        });

        // Surface engine stderr as warnings.
        let app_err = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                if !line.trim().is_empty() {
                    let _ = app_err.emit(
                        "rns-event",
                        serde_json::json!({"event":"log","level":"warn","message": line}),
                    );
                }
            }
        });

        Ok(())
    }

    /// Send one JSON command line to the engine.
    pub fn send(&mut self, value: serde_json::Value) -> Result<(), String> {
        let stdin = self
            .stdin
            .as_mut()
            .ok_or_else(|| "engine not running".to_string())?;
        let line = format!("{value}\n");
        stdin
            .write_all(line.as_bytes())
            .map_err(|e| format!("write to engine failed: {e}"))?;
        stdin.flush().map_err(|e| e.to_string())?;
        Ok(())
    }

    pub fn stop(&mut self) {
        if let Some(stdin) = self.stdin.as_mut() {
            let _ = stdin.write_all(b"{\"cmd\":\"shutdown\"}\n");
            let _ = stdin.flush();
        }
        self.stdin = None;
        if let Some(mut child) = self.child.take() {
            // Give it a moment to exit cleanly, then kill.
            std::thread::sleep(std::time::Duration::from_millis(300));
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
