//! ApiRgRPC — Reticulum (RNS/LXMF) desktop client.
//!
//! Architecture mirrors ApiNgRPC: a Tauri (Rust) shell drives an external
//! engine process. Here the engine is `rns-engine` (Python RNS + LXMF), managed
//! by `engine::Engine` and exposed to the UI through `commands`.

mod commands;
mod engine;

use std::sync::Mutex;

use engine::Engine;
use tauri::Manager;

pub struct AppState {
    pub engine: Mutex<Engine>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState {
            engine: Mutex::new(Engine::default()),
        })
        .invoke_handler(tauri::generate_handler![
            commands::engine_start,
            commands::engine_stop,
            commands::engine_is_running,
            commands::engine_status,
            commands::engine_address,
            commands::engine_announce,
            commands::engine_set_name,
            commands::engine_send,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.try_state::<AppState>() {
                    if let Ok(mut engine) = state.engine.lock() {
                        engine.stop();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running ApiRgRPC");
}
