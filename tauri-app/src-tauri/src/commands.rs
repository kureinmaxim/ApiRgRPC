//! Tauri commands — thin bridge from the UI to the Reticulum engine.
//!
//! Commands are fire-and-forget: results arrive asynchronously on the
//! frontend's `rns-event` listener (the same model as a chat/network stack).

use tauri::{AppHandle, State};

use crate::AppState;

#[tauri::command]
pub fn engine_start(app: AppHandle, state: State<AppState>, name: Option<String>) -> Result<(), String> {
    let display = name.unwrap_or_else(|| "ApiRgRPC".to_string());
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.start(&app, &display)
}

#[tauri::command]
pub fn engine_stop(state: State<AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.stop();
    Ok(())
}

#[tauri::command]
pub fn engine_is_running(state: State<AppState>) -> Result<bool, String> {
    let engine = state.engine.lock().map_err(|e| e.to_string())?;
    Ok(engine.is_running())
}

#[tauri::command]
pub fn engine_status(state: State<AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "status"}))
}

#[tauri::command]
pub fn engine_address(state: State<AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "address"}))
}

#[tauri::command]
pub fn engine_announce(state: State<AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "announce"}))
}

#[tauri::command]
pub fn engine_set_name(state: State<AppState>, name: String) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "set_name", "name": name}))
}

#[tauri::command]
pub fn engine_send(
    state: State<AppState>,
    peer: String,
    text: String,
    title: Option<String>,
) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({
        "cmd": "send",
        "peer": peer,
        "text": text,
        "title": title.unwrap_or_default(),
    }))
}

// ---- device-control (HA-мост по RNS) ---------------------------------------

#[tauri::command]
pub fn engine_dev_hash(state: State<AppState>, hash: String) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "dev_hash", "hash": hash}))
}

#[tauri::command]
pub fn engine_dev_status(state: State<AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "dev_status"}))
}

#[tauri::command]
pub fn engine_dev_ping(state: State<AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "dev_ping"}))
}

#[tauri::command]
pub fn engine_dev_read(state: State<AppState>, device: String) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "dev_read", "device": device}))
}

#[tauri::command]
pub fn engine_dev_write(state: State<AppState>, device: String, on: bool) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "dev_write", "device": device, "on": on}))
}

#[tauri::command]
pub fn engine_dev_stream(state: State<AppState>, max: Option<u32>) -> Result<(), String> {
    let mut engine = state.engine.lock().map_err(|e| e.to_string())?;
    engine.send(serde_json::json!({"cmd": "dev_stream", "max": max.unwrap_or(5)}))
}
