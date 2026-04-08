use serde_json::{json, Value};
use std::fs;
use std::net::UdpSocket;
use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::{command, AppHandle, Manager};
use uuid::Uuid;

fn project_root() -> PathBuf {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or(manifest)
}

fn core_root() -> PathBuf {
    project_root().join("aibutler-core")
}

fn voice_script_path() -> PathBuf {
    core_root().join("voice.py")
}

fn bridge_root() -> PathBuf {
    project_root().join("bridge")
}

fn bridge_script_path() -> PathBuf {
    bridge_root().join("server.py")
}

fn config_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(".aibutler").join("config.json")
}

fn bridge_config_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(".aibutler").join("bridge.json")
}

fn sidecar_path(app: &AppHandle) -> PathBuf {
    app.path()
        .resource_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("aibutler-runtime")
}

fn read_config() -> Value {
    let path = config_path();
    match fs::read_to_string(path) {
        Ok(raw) => serde_json::from_str(&raw).unwrap_or_else(|_| json!({})),
        Err(_) => json!({}),
    }
}

fn write_config(config: &Value) -> Result<(), String> {
    let path = config_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(path, serde_json::to_string_pretty(config).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())
}

fn read_bridge_config() -> Value {
    let path = bridge_config_path();
    match fs::read_to_string(path) {
        Ok(raw) => serde_json::from_str(&raw).unwrap_or_else(|_| json!({})),
        Err(_) => json!({}),
    }
}

fn write_bridge_config(config: &Value) -> Result<(), String> {
    let path = bridge_config_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(path, serde_json::to_string_pretty(config).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())
}

fn ensure_bridge_config() -> Result<Value, String> {
    let mut config = read_bridge_config();
    if !config.is_object() {
        config = json!({});
    }

    if config.get("pairing_token").and_then(Value::as_str).unwrap_or("").is_empty() {
        let token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
        config["pairing_token"] = Value::String(token);
    }
    if config.get("port").and_then(Value::as_u64).is_none() {
        config["port"] = Value::from(8765_u64);
    }

    write_bridge_config(&config)?;
    Ok(config)
}

fn detect_lan_ip() -> Option<String> {
    let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("8.8.8.8:80").ok()?;
    Some(socket.local_addr().ok()?.ip().to_string())
}

fn bridge_pairing_payload() -> Result<Value, String> {
    let config = ensure_bridge_config()?;
    let port = config.get("port").and_then(Value::as_u64).unwrap_or(8765);
    let url_hint = detect_lan_ip().map(|ip| format!("http://{ip}:{port}"));
    Ok(json!({
        "token": config.get("pairing_token").and_then(Value::as_str).unwrap_or(""),
        "token_hint": config.get("pairing_token").and_then(Value::as_str).map(|token| {
            if token.len() < 12 {
                token.to_string()
            } else {
                format!("{}...{}", &token[..6], &token[token.len() - 4..])
            }
        }),
        "port": port,
        "url_hint": url_hint,
        "bridge_state_path": bridge_config_path(),
    }))
}

fn runtime_command(app: &AppHandle) -> Command {
    let bundled = sidecar_path(app);
    if bundled.exists() {
        return Command::new(bundled);
    }

    let mut cmd = Command::new(std::env::var("AIBUTLER_PYTHON").unwrap_or_else(|_| "python3".to_string()));
    cmd.arg("-m")
        .arg("runtime")
        .current_dir(core_root())
        .env("PYTHONPATH", core_root());
    cmd
}

#[command]
fn get_runtime_status(app: AppHandle) -> Value {
    let config = read_config();
    json!({
        "runtime_available": sidecar_path(&app).exists() || core_root().exists(),
        "sidecar_available": sidecar_path(&app).exists(),
        "core_root": core_root(),
        "voice_script": voice_script_path(),
        "config": config,
    })
}

#[command]
fn save_config(key: String, value: String) -> Result<(), String> {
    let mut config = read_config();
    if !config.is_object() {
        config = json!({});
    }
    config[key] = Value::String(value);
    write_config(&config)
}

#[command]
fn load_config() -> Value {
    read_config()
}

#[command]
fn get_bridge_pairing() -> Result<Value, String> {
    bridge_pairing_payload()
}

#[command]
fn run_tool(
    app: AppHandle,
    tool: String,
    args: Option<String>,
    approved: Option<bool>,
    note: Option<String>,
) -> Result<String, String> {
    let mut cmd = runtime_command(&app);
    cmd.arg("tool-run")
        .arg("--tool-name")
        .arg(&tool)
        .arg("--args")
        .arg(args.unwrap_or_else(|| "{}".to_string()));

    if approved.unwrap_or(false) {
        cmd.arg("--approved");
    }
    if let Some(note) = note {
        if !note.is_empty() {
            cmd.arg("--note").arg(note);
        }
    }

    let output = cmd.output().map_err(|e| format!("Failed to run runtime: {e}"))?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Tool error: {err}"));
    }

    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

#[command]
fn run_agentic(app: AppHandle, objective: String) -> Result<String, String> {
    let output = runtime_command(&app)
        .arg("agentic-run")
        .arg("--objective")
        .arg(&objective)
        .output()
        .map_err(|e| format!("Failed to run agentic orchestrator: {e}"))?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Agentic error: {err}"));
    }

    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

#[command]
fn run_core_agent(app: AppHandle, prompt: String) -> Result<String, String> {
    let output = runtime_command(&app)
        .arg("core-agent-run")
        .arg("--prompt")
        .arg(&prompt)
        .output()
        .map_err(|e| format!("Failed to run core agent: {e}"))?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Core agent error: {err}"));
    }

    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

#[command]
fn open_system_settings(pane: String) -> Result<(), String> {
    let url = match pane.as_str() {
        "accessibility" => {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        }
        "screen-recording" => {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        }
        "automation" => {
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
        }
        _ => return Err(format!("Unknown settings pane: {pane}")),
    };
    open::that(url).map_err(|e| e.to_string())
}

#[command]
fn start_voice_loop() -> Result<(), String> {
    let output = Command::new(std::env::var("AIBUTLER_PYTHON").unwrap_or_else(|_| "python3".to_string()))
        .arg(voice_script_path())
        .current_dir(core_root())
        .spawn()
        .map_err(|e| format!("Failed to launch voice loop: {e}"))?;

    let _ = output;
    Ok(())
}

#[command]
fn start_bridge() -> Result<Value, String> {
    let pairing = bridge_pairing_payload()?;

    Command::new(std::env::var("AIBUTLER_PYTHON").unwrap_or_else(|_| "python3".to_string()))
        .arg(bridge_script_path())
        .current_dir(bridge_root())
        .env("AIBUTLER_BRIDGE_ALLOW_LAN", "1")
        .spawn()
        .map_err(|e| format!("Failed to launch bridge: {e}"))?;

    Ok(pairing)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            get_runtime_status,
            save_config,
            load_config,
            get_bridge_pairing,
            run_tool,
            run_agentic,
            run_core_agent,
            open_system_settings,
            start_voice_loop,
            start_bridge,
        ])
        .run(tauri::generate_context!())
        .expect("error while running aiButler");
}
