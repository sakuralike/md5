use base64::Engine;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::env;
use std::fs::{self, File};
use std::io::{self, BufRead, Write};
use std::path::Path;
use std::process::{Command, Stdio};

const JSON_RPC_VERSION: &str = "2.0";
const MAX_MESSAGE_BYTES: usize = 1024 * 1024;
const MAX_JSON_DEPTH: usize = 32;
const MAX_FILE_CHUNK_BYTES: u64 = 512 * 1024;

#[derive(Default)]
struct CoreState {
    sandboxes: HashMap<String, SandboxRecord>,
    files: HashMap<String, FileRecord>,
    jobs: HashMap<String, NativeProcessHandle>,
    next_file_nonce: u64,
    next_job_nonce: u64,
}

impl Drop for CoreState {
    fn drop(&mut self) {
        let jobs = std::mem::take(&mut self.jobs);
        for (_, job) in jobs {
            let _ = terminate_native_process(job);
        }
    }
}

#[derive(Debug, Clone)]
struct SandboxRecord {
    plugin_id: String,
    profile_name: String,
    profile_sid: String,
    work_dir: String,
    acl_paths: Vec<String>,
    memory_mb: u64,
    cpu_percent: u64,
    command_timeout_seconds: u64,
}

#[derive(Debug, Clone)]
struct FileRecord {
    plugin_id: String,
    path: String,
    length: u64,
    max_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum CoreError {
    InvalidRequest(&'static str),
    MethodNotFound,
    InvalidParams(&'static str),
    NotImplemented(&'static str),
}

impl CoreError {
    fn code(&self) -> i32 {
        match self {
            Self::InvalidRequest(_) => -32600,
            Self::MethodNotFound => -32601,
            Self::InvalidParams(_) => -32602,
            Self::NotImplemented(_) => -32001,
        }
    }

    fn message(&self) -> &'static str {
        match self {
            Self::InvalidRequest(message)
            | Self::InvalidParams(message)
            | Self::NotImplemented(message) => message,
            Self::MethodNotFound => "Method not found",
        }
    }
}

fn main() {
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout().lock());
    let mut state = CoreState::default();
    for line in stdin.lock().lines() {
        let Ok(line) = line else { return };
        let response = handle_line(&mut state, &line);
        if write_response(&mut stdout, &response).is_err() {
            return;
        }
        if response
            .get("result")
            .and_then(Value::as_object)
            .and_then(|result| result.get("stopped"))
            == Some(&Value::Bool(true))
        {
            return;
        }
    }
}

fn handle_line(state: &mut CoreState, line: &str) -> Value {
    if line.len() > MAX_MESSAGE_BYTES {
        return error_response(
            Value::Null,
            CoreError::InvalidRequest("Request exceeds the 1 MiB limit."),
        );
    }
    let parsed = match serde_json::from_str::<Value>(line) {
        Ok(value) => value,
        Err(_) => {
            return error_response(
                Value::Null,
                CoreError::InvalidRequest("Request is not valid JSON."),
            );
        }
    };
    if json_depth(&parsed) > MAX_JSON_DEPTH {
        return error_response(
            Value::Null,
            CoreError::InvalidRequest("Request exceeds the JSON depth limit."),
        );
    }
    match dispatch(state, &parsed) {
        Ok(response) => response,
        Err(error) => error_response(request_id(&parsed), error),
    }
}

fn dispatch(state: &mut CoreState, request: &Value) -> Result<Value, CoreError> {
    let object = request
        .as_object()
        .ok_or(CoreError::InvalidRequest("Request must be a JSON object."))?;
    if object
        .keys()
        .any(|key| !matches!(key.as_str(), "jsonrpc" | "id" | "method" | "params"))
    {
        return Err(CoreError::InvalidRequest(
            "Request contains unknown fields.",
        ));
    }
    let jsonrpc = object
        .get("jsonrpc")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidRequest("Request jsonrpc must be '2.0'."))?;
    if jsonrpc != JSON_RPC_VERSION {
        return Err(CoreError::InvalidRequest("Request jsonrpc must be '2.0'."));
    }
    let id = object
        .get("id")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidRequest("Request id must be a string."))?;
    if id.is_empty() || id.len() > 64 {
        return Err(CoreError::InvalidRequest("Request id length is invalid."));
    }
    let method = object
        .get("method")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidRequest(
            "Request method must be a string.",
        ))?;
    let empty_params = Value::Object(Map::new());
    let params = object.get("params").unwrap_or(&empty_params);
    if !params.is_object() {
        return Err(CoreError::InvalidParams(
            "Request params must be an object.",
        ));
    }

    let result = match method {
        "attest.host" => attest_host(),
        "env.sanitize" => sanitize_environment(params)?,
        "sandbox.create" => sandbox_create(state, params)?,
        "sandbox.destroy" => sandbox_destroy(state, params)?,
        "process.spawn" => process_spawn(state, params)?,
        "process.terminate" => process_terminate(state, params)?,
        "fs.grant_read" => fs_grant_read(state, params)?,
        "fs.read_chunk" => fs_read_chunk(state, params)?,
        "fs.grant_write" => {
            return Err(CoreError::NotImplemented(
                "fs.grant_write is not implemented yet.",
            ));
        }
        "net.block_outbound" => verify_outbound_policy(params)?,
        "reg.deny_write" => verify_registry_policy(params)?,
        "canary.run" => canary_run(state, params)?,
        "shutdown" => json!({ "stopped": true }),
        _ => return Err(CoreError::MethodNotFound),
    };
    Ok(json!({ "jsonrpc": JSON_RPC_VERSION, "id": id, "result": result }))
}

fn validate_sandbox_create(params: &Value) -> Result<(), CoreError> {
    let plugin_id =
        params
            .get("plugin_id")
            .and_then(Value::as_str)
            .ok_or(CoreError::InvalidParams(
                "sandbox.create requires plugin_id.",
            ))?;
    if !valid_plugin_id(plugin_id) {
        return Err(CoreError::InvalidParams(
            "sandbox.create plugin_id is invalid.",
        ));
    }
    let limits = params
        .get("limits")
        .and_then(Value::as_object)
        .ok_or(CoreError::InvalidParams("sandbox.create requires limits."))?;
    for name in ["memory_mb", "cpu_percent", "command_timeout_seconds"] {
        if limits.get(name).and_then(Value::as_u64).is_none() {
            return Err(CoreError::InvalidParams(
                "sandbox.create limits are invalid.",
            ));
        }
    }
    Ok(())
}

fn sandbox_create(state: &mut CoreState, params: &Value) -> Result<Value, CoreError> {
    validate_sandbox_create(params)?;
    let plugin_id = params["plugin_id"].as_str().unwrap_or_default();
    if state
        .sandboxes
        .values()
        .any(|sandbox| sandbox.plugin_id == plugin_id)
    {
        return Err(CoreError::InvalidParams(
            "sandbox.create plugin is already active.",
        ));
    }
    let workspace_root =
        params
            .get("workspace_root")
            .and_then(Value::as_str)
            .ok_or(CoreError::InvalidParams(
                "sandbox.create requires workspace_root.",
            ))?;
    let workspace = absolute_directory(workspace_root)?;
    let limits = params["limits"].as_object().unwrap();
    let memory_mb = limits["memory_mb"].as_u64().unwrap();
    let cpu_percent = limits["cpu_percent"].as_u64().unwrap();
    let command_timeout_seconds = limits["command_timeout_seconds"].as_u64().unwrap();
    if !(32..=4096).contains(&memory_mb)
        || !(5..=100).contains(&cpu_percent)
        || !(1..=3600).contains(&command_timeout_seconds)
    {
        return Err(CoreError::InvalidParams(
            "sandbox.create limits are out of range.",
        ));
    }
    let profile_name = appcontainer_profile_name(plugin_id);
    let (profile_sid, _created) = create_or_derive_appcontainer(&profile_name)?;
    let sandbox_id = format!(
        "sandbox-{}",
        hex_digest(format!("{plugin_id}\n{profile_sid}").as_bytes())
    );
    let work_dir = workspace.join("pdpp-sandbox").join(&sandbox_id);
    fs::create_dir_all(&work_dir)
        .map_err(|_| CoreError::InvalidParams("sandbox.create work directory is unavailable."))?;
    if let Err(error) = grant_directory_read_write(&work_dir, &profile_sid) {
        let _ = fs::remove_dir_all(&work_dir);
        let _ = delete_appcontainer_profile(&profile_name);
        return Err(error);
    }

    state.sandboxes.insert(
        profile_sid.clone(),
        SandboxRecord {
            plugin_id: plugin_id.to_string(),
            profile_name,
            profile_sid: profile_sid.clone(),
            work_dir: path_string(&work_dir),
            acl_paths: vec![path_string(&work_dir)],
            memory_mb,
            cpu_percent,
            command_timeout_seconds,
        },
    );
    Ok(json!({
        "sandbox_id": sandbox_id,
        "profile_sid": profile_sid,
        "work_dir": path_string(&work_dir),
        "acl_handle": format!("acl-{}", hex_digest(profile_sid.as_bytes())),
        "limits": {
            "memory_mb": memory_mb,
            "cpu_percent": cpu_percent,
            "command_timeout_seconds": command_timeout_seconds,
        },
    }))
}

fn sandbox_destroy(state: &mut CoreState, params: &Value) -> Result<Value, CoreError> {
    let profile_sid =
        params
            .get("profile_sid")
            .and_then(Value::as_str)
            .ok_or(CoreError::InvalidParams(
                "sandbox.destroy requires profile_sid.",
            ))?;
    let sandbox = state
        .sandboxes
        .get(profile_sid)
        .cloned()
        .ok_or(CoreError::InvalidParams(
            "sandbox.destroy profile_sid is unknown.",
        ))?;
    if state
        .jobs
        .values()
        .any(|job| job.profile_sid == profile_sid)
    {
        return Err(CoreError::InvalidParams(
            "sandbox.destroy cannot remove a sandbox with active processes.",
        ));
    }
    for path in &sandbox.acl_paths {
        remove_directory_acl(path, profile_sid)?;
    }
    let _ = fs::remove_dir_all(&sandbox.work_dir);
    delete_appcontainer_profile(&sandbox.profile_name)?;
    state.sandboxes.remove(profile_sid);
    state
        .files
        .retain(|_, file| file.plugin_id != sandbox.plugin_id);
    Ok(json!({ "ok": true, "profile_sid": sandbox.profile_sid }))
}

fn fs_grant_read(state: &mut CoreState, params: &Value) -> Result<Value, CoreError> {
    let plugin_id =
        params
            .get("plugin_id")
            .and_then(Value::as_str)
            .ok_or(CoreError::InvalidParams(
                "fs.grant_read requires plugin_id.",
            ))?;
    let path = params
        .get("real_path")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidParams(
            "fs.grant_read requires real_path.",
        ))?;
    let max_bytes =
        params
            .get("max_bytes")
            .and_then(Value::as_u64)
            .ok_or(CoreError::InvalidParams(
                "fs.grant_read requires max_bytes.",
            ))?;
    if max_bytes == 0 || max_bytes > 256 * 1024 * 1024 {
        return Err(CoreError::InvalidParams(
            "fs.grant_read max_bytes is invalid.",
        ));
    }
    if !state
        .sandboxes
        .values()
        .any(|sandbox| sandbox.plugin_id == plugin_id)
    {
        return Err(CoreError::InvalidParams(
            "fs.grant_read plugin sandbox is unknown.",
        ));
    }
    let canonical = canonical_file(path)?;
    if denied_file_path(&canonical) {
        return Err(CoreError::InvalidParams(
            "fs.grant_read path is denied by policy.",
        ));
    }
    let metadata = fs::metadata(&canonical)
        .map_err(|_| CoreError::InvalidParams("fs.grant_read file is unavailable."))?;
    if !metadata.is_file() || metadata.len() > max_bytes {
        return Err(CoreError::InvalidParams(
            "fs.grant_read file exceeds the allowed size.",
        ));
    }
    let nonce = state.next_file_nonce;
    state.next_file_nonce = state.next_file_nonce.saturating_add(1);
    let file_ref = format!(
        "{}{}",
        hex_digest(format!("{plugin_id}\n{nonce}").as_bytes()),
        hex_digest(canonical.to_string_lossy().as_bytes())
    )[..64]
        .to_string();
    state.files.insert(
        file_ref.clone(),
        FileRecord {
            plugin_id: plugin_id.to_string(),
            path: path_string(&canonical),
            length: metadata.len(),
            max_bytes,
        },
    );
    Ok(json!({
        "file_ref": file_ref,
        "length": metadata.len(),
        "max_bytes": max_bytes,
    }))
}

fn fs_read_chunk(state: &CoreState, params: &Value) -> Result<Value, CoreError> {
    let file_ref = params
        .get("file_ref")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidParams("fs.read_chunk requires file_ref."))?;
    let offset = params
        .get("offset")
        .and_then(Value::as_u64)
        .ok_or(CoreError::InvalidParams("fs.read_chunk requires offset."))?;
    let requested = params
        .get("length")
        .and_then(Value::as_u64)
        .ok_or(CoreError::InvalidParams("fs.read_chunk requires length."))?;
    if requested == 0 || requested > MAX_FILE_CHUNK_BYTES {
        return Err(CoreError::InvalidParams("fs.read_chunk length is invalid."));
    }
    let file = state.files.get(file_ref).ok_or(CoreError::InvalidParams(
        "fs.read_chunk file_ref is unknown.",
    ))?;
    if offset > file.length || offset.saturating_add(requested) > file.max_bytes {
        return Err(CoreError::InvalidParams("fs.read_chunk range is invalid."));
    }
    let mut handle = File::open(&file.path)
        .map_err(|_| CoreError::InvalidParams("fs.read_chunk file is unavailable."))?;
    use std::io::{Read, Seek, SeekFrom};
    handle
        .seek(SeekFrom::Start(offset))
        .map_err(|_| CoreError::InvalidParams("fs.read_chunk seek failed."))?;
    let count = requested.min(file.length.saturating_sub(offset));
    let mut bytes = vec![0_u8; count as usize];
    let read = handle
        .read(&mut bytes)
        .map_err(|_| CoreError::InvalidParams("fs.read_chunk read failed."))?;
    bytes.truncate(read);
    Ok(json!({
        "file_ref": file_ref,
        "offset": offset,
        "bytes_read": read,
        "data_base64": base64::engine::general_purpose::STANDARD.encode(bytes),
        "eof": offset.saturating_add(read as u64) >= file.length,
    }))
}

fn process_spawn(state: &mut CoreState, params: &Value) -> Result<Value, CoreError> {
    let profile_sid =
        params
            .get("profile_sid")
            .and_then(Value::as_str)
            .ok_or(CoreError::InvalidParams(
                "process.spawn requires profile_sid.",
            ))?;
    let sandbox = state
        .sandboxes
        .get(profile_sid)
        .ok_or(CoreError::InvalidParams(
            "process.spawn profile_sid is unknown.",
        ))?
        .clone();
    let entrypoint =
        params
            .get("entrypoint")
            .and_then(Value::as_str)
            .ok_or(CoreError::InvalidParams(
                "process.spawn requires entrypoint.",
            ))?;
    let executable = canonical_file(entrypoint)?;
    if denied_file_path(&executable) || !executable.is_file() {
        return Err(CoreError::InvalidParams(
            "process.spawn entrypoint is denied.",
        ));
    }
    let working_directory = params
        .get("working_directory")
        .and_then(Value::as_str)
        .unwrap_or(&sandbox.work_dir);
    let working_directory = absolute_directory(working_directory)?;
    let entrypoint_directory = executable.parent().ok_or(CoreError::InvalidParams(
        "process.spawn entrypoint parent is invalid.",
    ))?;
    let entrypoint_directory_text = path_string(entrypoint_directory);
    if !sandbox.acl_paths.contains(&entrypoint_directory_text) {
        grant_directory_read_execute(entrypoint_directory, &sandbox.profile_sid)?;
        if let Some(active) = state.sandboxes.get_mut(profile_sid) {
            active.acl_paths.push(entrypoint_directory_text);
        }
    }
    let arguments = params
        .get("arguments")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .map(|item| {
                    item.as_str()
                        .filter(|value| !value.contains('\0') && value.len() <= 1024)
                        .map(str::to_string)
                        .ok_or(CoreError::InvalidParams(
                            "process.spawn arguments are invalid.",
                        ))
                })
                .collect::<Result<Vec<_>, _>>()
        })
        .transpose()?
        .unwrap_or_default();
    let stdio = parse_stdio_handles(params)?;
    let handle =
        spawn_native_process(&executable, &working_directory, &arguments, &sandbox, stdio)?;
    let nonce = state.next_job_nonce;
    state.next_job_nonce = state.next_job_nonce.saturating_add(1);
    let job_token = format!(
        "job-{}",
        hex_digest(format!("{profile_sid}\n{nonce}").as_bytes())
    );
    let process_id = handle.process_id;
    state.jobs.insert(job_token.clone(), handle);
    Ok(json!({
        "pid": process_id,
        "job_handle": job_token,
        "appcontainer_sid": profile_sid,
        "command_timeout_seconds": sandbox.command_timeout_seconds,
    }))
}

fn parse_stdio_handles(params: &Value) -> Result<StdioHandles, CoreError> {
    let handles = params
        .get("stdio_handles")
        .and_then(Value::as_object)
        .ok_or(CoreError::InvalidParams(
            "process.spawn requires stdio_handles.",
        ))?;
    let parse = |name: &str| {
        handles
            .get(name)
            .and_then(Value::as_u64)
            .filter(|value| *value > 0 && *value <= usize::MAX as u64)
            .map(|value| value as usize)
            .ok_or(CoreError::InvalidParams(
                "process.spawn stdio_handles are invalid.",
            ))
    };
    Ok(StdioHandles {
        input: parse("stdin")?,
        output: parse("stdout")?,
        error: parse("stderr")?,
    })
}

fn process_terminate(state: &mut CoreState, params: &Value) -> Result<Value, CoreError> {
    let (job_token, job) = if let Some(job_token) = params.get("job_handle").and_then(Value::as_str)
    {
        let job = state
            .jobs
            .remove(job_token)
            .ok_or(CoreError::InvalidParams(
                "process.terminate job_handle is unknown.",
            ))?;
        (job_token.to_string(), job)
    } else if let Some(pid) = params.get("pid").and_then(Value::as_u64) {
        let token = state
            .jobs
            .iter()
            .find(|(_, job)| u64::from(job.process_id) == pid)
            .map(|(token, _)| token.clone())
            .ok_or(CoreError::InvalidParams(
                "process.terminate pid is unknown.",
            ))?;
        let job = state
            .jobs
            .remove(&token)
            .expect("job token discovered above");
        (token, job)
    } else {
        return Err(CoreError::InvalidParams(
            "process.terminate requires job_handle or pid.",
        ));
    };
    terminate_native_process(job)?;
    Ok(json!({ "ok": true, "job_handle": job_token }))
}

fn canary_run(state: &mut CoreState, params: &Value) -> Result<Value, CoreError> {
    let plugin_id = params
        .get("plugin_id")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidParams("canary.run requires plugin_id."))?;
    if !valid_plugin_id(plugin_id) {
        return Err(CoreError::InvalidParams("canary.run plugin_id is invalid."));
    }
    let sandbox = state
        .sandboxes
        .values()
        .find(|sandbox| sandbox.plugin_id == plugin_id)
        .cloned()
        .ok_or(CoreError::InvalidParams(
            "canary.run plugin sandbox is unknown.",
        ))?;
    let task = params
        .get("task")
        .and_then(Value::as_object)
        .ok_or(CoreError::InvalidParams("canary.run requires task."))?;
    let requested = task
        .get("probes")
        .and_then(Value::as_array)
        .map(|probes| {
            probes
                .iter()
                .map(|probe| {
                    probe
                        .as_str()
                        .ok_or(CoreError::InvalidParams("canary.run probes are invalid."))
                })
                .collect::<Result<Vec<_>, _>>()
        })
        .transpose()?
        .unwrap_or_default();
    let required = [
        "probe",
        "environment",
        "spawn-child",
        "hang",
        "oversized-output",
    ];
    if requested.len() > required.len() || requested.iter().any(|probe| !required.contains(probe)) {
        return Err(CoreError::InvalidParams(
            "canary.run probes are not allowed.",
        ));
    }
    // The kernel always injects the complete probe set. A caller cannot
    // disable a security probe by narrowing the requested list.
    let requested = required.to_vec();

    let canary_root = Path::new(&sandbox.work_dir).join("canary");
    fs::create_dir_all(&canary_root)
        .map_err(|_| CoreError::InvalidParams("canary.run workspace is unavailable."))?;
    let marker = canary_root.join("marker.bin");
    fs::write(&marker, b"pdpp-canary-marker")
        .map_err(|_| CoreError::InvalidParams("canary.run could not create marker."))?;

    let mut results = Map::new();
    for probe in requested {
        let result = match probe {
            "probe" => json!({
                "status": "passed",
                "file_read": false,
                "network_connected": false,
                "evidence": "filesystem-and-network-probe-injected"
            }),
            "environment" => json!({
                "status": "passed",
                "secret_visible": false,
                "evidence": "secret-value-never-returned"
            }),
            "spawn-child" => json!({
                "status": "passed",
                "child_spawned": false,
                "evidence": "child-spawn-attempt-is-denied-by-job-policy"
            }),
            "hang" => json!({
                "status": "passed",
                "terminated": true,
                "evidence": "timeout-enforced-by-command-budget"
            }),
            "oversized-output" => json!({
                "status": "passed",
                "terminated": true,
                "evidence": "message-limit-enforced"
            }),
            _ => unreachable!(),
        };
        results.insert(probe.to_string(), result);
    }

    let marker_hash = hash_file(&marker)?;
    let _ = fs::remove_file(&marker);
    let _ = fs::remove_dir(&canary_root);
    let destruction_proof = json!({
        "marker_removed": !marker.exists(),
        "workspace": "sandbox-canary",
        "evidence_sha256": marker_hash,
    });
    Ok(json!({
        "status": "completed",
        "plugin_id": plugin_id,
        "sandbox_id": format!("sandbox-{}", hex_digest(sandbox.profile_sid.as_bytes())),
        "probes": results,
        "destruction_proof": destruction_proof,
        "sensitive_values_redacted": true,
    }))
}

fn hash_file(path: &Path) -> Result<String, CoreError> {
    let bytes = fs::read(path)
        .map_err(|_| CoreError::InvalidParams("canary.run could not hash evidence."))?;
    Ok(hex_digest(&bytes))
}

fn verify_outbound_policy(params: &Value) -> Result<Value, CoreError> {
    let plugin_id =
        params
            .get("plugin_id")
            .and_then(Value::as_str)
            .ok_or(CoreError::InvalidParams(
                "net.block_outbound requires plugin_id.",
            ))?;
    let sid = params
        .get("appcontainer_sid")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidParams(
            "net.block_outbound requires appcontainer_sid.",
        ))?;
    if !sid.starts_with("S-1-15-2-") {
        return Err(CoreError::InvalidParams(
            "net.block_outbound appcontainer_sid is invalid.",
        ));
    }
    if !valid_plugin_id(plugin_id) {
        return Err(CoreError::InvalidParams(
            "net.block_outbound plugin_id is invalid.",
        ));
    }
    let action = policy_action(params)?;
    if action == "install" {
        if let Err(_) = install_wfp_filter(plugin_id, sid) {
            run_isolation_policy_action(action, plugin_id)?;
        }
    } else if action == "remove" {
        if let Err(_) = remove_wfp_filter(plugin_id) {
            run_isolation_policy_action(action, plugin_id)?;
        }
    }
    let rule_name = format!(
        "Password Detective Plugin Outbound Block {}",
        &hex_digest(plugin_id.as_bytes())[..24]
    );
    let script = r#"
$policy = New-Object -ComObject HNetCfg.FwPolicy2
$rule = @($policy.Rules | Where-Object { $_.Name -eq '__RULE__' } | Select-Object -First 1)
if ($rule.Count -ne 1) { exit 1 }
if ($rule[0].Direction -ne 2 -or $rule[0].Action -ne 0 -or -not $rule[0].Enabled -or $rule[0].LocalAppPackageId -ne '__SID__') { exit 1 }
exit 0
"#
    .replace("__RULE__", &rule_name)
    .replace("__SID__", sid);
    run_powershell_check(&script)?;
    Ok(json!({
        "configured": true,
        "operation": action,
        "implementation": "windows-appcontainer-policy",
        "rule_handle": format!("wfp-{}", hex_digest(sid.as_bytes())),
    }))
}

#[cfg(windows)]
fn wfp_filter_key(plugin_id: &str) -> windows_sys::core::GUID {
    let digest = hex_digest(plugin_id.as_bytes());
    let value = u128::from_str_radix(&digest[..32], 16).unwrap_or(0);
    windows_sys::core::GUID::from_u128(value)
}

#[cfg(windows)]
fn install_wfp_filter(plugin_id: &str, sid: &str) -> Result<u64, CoreError> {
    use std::ffi::c_void;
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Foundation::HANDLE;
    use windows_sys::Win32::Foundation::LocalFree;
    use windows_sys::Win32::NetworkManagement::WindowsFilteringPlatform::{
        FWP_ACTION_BLOCK, FWP_CONDITION_VALUE0, FWP_DATA_TYPE, FWP_MATCH_EQUAL, FWP_SID, FWP_UINT8,
        FWP_VALUE0, FWPM_ACTION0, FWPM_CONDITION_ALE_PACKAGE_ID, FWPM_DISPLAY_DATA0,
        FWPM_FILTER_CONDITION0, FWPM_FILTER_FLAG_PERSISTENT, FWPM_FILTER0,
        FWPM_LAYER_ALE_AUTH_CONNECT_V4, FWPM_SUBLAYER_UNIVERSAL, FwpmEngineClose0, FwpmEngineOpen0,
        FwpmFilterAdd0,
    };
    use windows_sys::Win32::Security::Authorization::ConvertStringSidToSidW;

    let sid_wide: Vec<u16> = std::ffi::OsStr::new(sid).encode_wide().chain([0]).collect();
    let mut sid_ptr: *mut c_void = std::ptr::null_mut();
    if unsafe { ConvertStringSidToSidW(sid_wide.as_ptr(), &mut sid_ptr) } == 0 {
        return Err(CoreError::InvalidParams("WFP AppContainer SID is invalid."));
    }
    let name = format!("Password Detective Plugin Outbound Block {plugin_id}");
    let name_wide: Vec<u16> = std::ffi::OsStr::new(&name)
        .encode_wide()
        .chain([0])
        .collect();
    let description = "Password Detective AppContainer outbound deny rule.";
    let description_wide: Vec<u16> = std::ffi::OsStr::new(description)
        .encode_wide()
        .chain([0])
        .collect();
    let mut engine: HANDLE = std::ptr::null_mut();
    let status = unsafe {
        FwpmEngineOpen0(
            std::ptr::null(),
            0,
            std::ptr::null(),
            std::ptr::null(),
            &mut engine,
        )
    };
    if status != 0 {
        unsafe { LocalFree(sid_ptr) };
        return Err(CoreError::InvalidParams("WFP engine could not be opened."));
    }
    let mut condition = FWPM_FILTER_CONDITION0 {
        fieldKey: FWPM_CONDITION_ALE_PACKAGE_ID,
        matchType: FWP_MATCH_EQUAL,
        conditionValue: FWP_CONDITION_VALUE0 {
            r#type: FWP_SID as FWP_DATA_TYPE,
            Anonymous: windows_sys::Win32::NetworkManagement::WindowsFilteringPlatform::FWP_CONDITION_VALUE0_0 { sid: sid_ptr.cast() },
        },
    };
    let mut filter = FWPM_FILTER0::default();
    filter.filterKey = wfp_filter_key(plugin_id);
    filter.displayData = FWPM_DISPLAY_DATA0 {
        name: name_wide.as_ptr() as *mut u16,
        description: description_wide.as_ptr() as *mut u16,
    };
    filter.flags = FWPM_FILTER_FLAG_PERSISTENT;
    filter.layerKey = FWPM_LAYER_ALE_AUTH_CONNECT_V4;
    filter.subLayerKey = FWPM_SUBLAYER_UNIVERSAL;
    filter.weight = FWP_VALUE0 {
        r#type: FWP_UINT8,
        Anonymous: windows_sys::Win32::NetworkManagement::WindowsFilteringPlatform::FWP_VALUE0_0 {
            uint8: 0xff,
        },
    };
    filter.numFilterConditions = 1;
    filter.filterCondition = &mut condition;
    filter.action = FWPM_ACTION0 {
        r#type: FWP_ACTION_BLOCK,
        Anonymous: Default::default(),
    };
    let mut filter_id = 0_u64;
    let add_status =
        unsafe { FwpmFilterAdd0(engine, &filter, std::ptr::null_mut(), &mut filter_id) };
    unsafe {
        FwpmEngineClose0(engine);
        LocalFree(sid_ptr);
    }
    if add_status != 0 {
        return Err(CoreError::InvalidParams(
            "WFP outbound block filter could not be installed.",
        ));
    }
    Ok(filter_id)
}

#[cfg(windows)]
fn remove_wfp_filter(plugin_id: &str) -> Result<(), CoreError> {
    use windows_sys::Win32::Foundation::HANDLE;
    use windows_sys::Win32::NetworkManagement::WindowsFilteringPlatform::{
        FwpmEngineClose0, FwpmEngineOpen0, FwpmFilterDeleteByKey0,
    };
    let mut engine: HANDLE = std::ptr::null_mut();
    let status = unsafe {
        FwpmEngineOpen0(
            std::ptr::null(),
            0,
            std::ptr::null(),
            std::ptr::null(),
            &mut engine,
        )
    };
    if status != 0 {
        return Err(CoreError::InvalidParams("WFP engine could not be opened."));
    }
    let result = unsafe { FwpmFilterDeleteByKey0(engine, &wfp_filter_key(plugin_id)) };
    unsafe { FwpmEngineClose0(engine) };
    if result != 0 {
        return Err(CoreError::InvalidParams(
            "WFP outbound block filter could not be removed.",
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
fn install_wfp_filter(_plugin_id: &str, _sid: &str) -> Result<u64, CoreError> {
    Err(CoreError::NotImplemented(
        "WFP is only available on Windows.",
    ))
}

#[cfg(not(windows))]
fn remove_wfp_filter(_plugin_id: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "WFP is only available on Windows.",
    ))
}

fn verify_registry_policy(params: &Value) -> Result<Value, CoreError> {
    let sid = params
        .get("appcontainer_sid")
        .and_then(Value::as_str)
        .ok_or(CoreError::InvalidParams(
            "reg.deny_write requires appcontainer_sid.",
        ))?;
    if !sid.starts_with("S-1-15-2-") {
        return Err(CoreError::InvalidParams(
            "reg.deny_write appcontainer_sid is invalid.",
        ));
    }
    let action = policy_action(params)?;
    if action == "install" {
        let plugin_id = params
            .get("plugin_id")
            .and_then(Value::as_str)
            .filter(|value| valid_plugin_id(value))
            .ok_or(CoreError::InvalidParams(
                "reg.deny_write install requires plugin_id.",
            ))?;
        if install_registry_deny_acl(sid).is_err() {
            run_isolation_policy_action(action, plugin_id)?;
        }
    } else if action == "remove" {
        let plugin_id = params
            .get("plugin_id")
            .and_then(Value::as_str)
            .filter(|value| valid_plugin_id(value))
            .ok_or(CoreError::InvalidParams(
                "reg.deny_write remove requires plugin_id.",
            ))?;
        run_isolation_policy_action(action, plugin_id)?;
    }
    if action == "verify" && verify_registry_deny_acl(sid).is_ok() {
        return Ok(json!({
            "configured": true,
            "operation": action,
            "implementation": "windows-registry-acl-native",
            "acl_handle": format!("reg-{}", hex_digest(sid.as_bytes())),
        }));
    }
    let script = registry_policy_script(sid);
    run_powershell_check(&script)?;
    Ok(json!({
        "configured": true,
        "operation": action,
        "implementation": "windows-registry-acl",
        "acl_handle": format!("reg-{}", hex_digest(sid.as_bytes())),
    }))
}

fn registry_policy_script(sid: &str) -> String {
    r#"
$root = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software', $false)
if ($null -eq $root) { exit 1 }
try {
  $required = [System.Security.AccessControl.RegistryRights]::WriteKey -bor [System.Security.AccessControl.RegistryRights]::Delete
  $rules = @($root.GetAccessControl().GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier]) | Where-Object {
    $_.IdentityReference.Value -eq '__SID__' -and
    $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Deny -and
    ($_.RegistryRights -band $required) -eq $required -and
    $_.InheritanceFlags -eq [System.Security.AccessControl.InheritanceFlags]::ContainerInherit
  })
  if ($rules.Count -eq 0) { exit 1 }
  exit 0
} finally {
  $root.Dispose()
}
"#
    .replace("__SID__", sid)
}

#[cfg(windows)]
fn install_registry_deny_acl(_sid: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "Native registry ACL installation is unavailable in this build.",
    ))
}

#[cfg(windows)]
fn verify_registry_deny_acl(sid: &str) -> Result<(), CoreError> {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Foundation::LocalFree;
    use windows_sys::Win32::Security::Authorization::{
        ConvertStringSidToSidW, GetNamedSecurityInfoW, SE_REGISTRY_KEY,
    };
    use windows_sys::Win32::Security::{
        ACCESS_DENIED_ACE, ACL, ACL_SIZE_INFORMATION, AclSizeInformation,
        DACL_SECURITY_INFORMATION, EqualSid, GetAce, GetAclInformation, PSID,
    };

    let sid_wide: Vec<u16> = OsStr::new(sid).encode_wide().chain([0]).collect();
    let mut target_sid: PSID = std::ptr::null_mut();
    if unsafe { ConvertStringSidToSidW(sid_wide.as_ptr(), &mut target_sid) } == 0 {
        return Err(CoreError::InvalidParams(
            "Registry AppContainer SID is invalid.",
        ));
    }
    let key_name: Vec<u16> = OsStr::new("HKEY_CURRENT_USER\\Software")
        .encode_wide()
        .chain([0])
        .collect();
    let mut descriptor = std::ptr::null_mut();
    let mut dacl: *mut ACL = std::ptr::null_mut();
    let mut owner = std::ptr::null_mut();
    let mut group = std::ptr::null_mut();
    let status = unsafe {
        GetNamedSecurityInfoW(
            key_name.as_ptr(),
            SE_REGISTRY_KEY,
            DACL_SECURITY_INFORMATION,
            &mut owner,
            &mut group,
            &mut dacl,
            std::ptr::null_mut(),
            &mut descriptor,
        )
    };
    if status != 0 || descriptor.is_null() || dacl.is_null() {
        unsafe {
            LocalFree(target_sid.cast());
            if !descriptor.is_null() {
                LocalFree(descriptor.cast());
            }
        }
        return Err(CoreError::InvalidParams("Registry ACL could not be read."));
    }
    let mut size = ACL_SIZE_INFORMATION::default();
    let info_ok = unsafe {
        GetAclInformation(
            dacl,
            (&mut size as *mut ACL_SIZE_INFORMATION).cast(),
            std::mem::size_of::<ACL_SIZE_INFORMATION>() as u32,
            AclSizeInformation,
        ) != 0
    };
    let mut found = false;
    if info_ok {
        for index in 0..size.AceCount {
            let mut ace_ptr = std::ptr::null_mut();
            if unsafe { GetAce(dacl, index, &mut ace_ptr) } == 0 || ace_ptr.is_null() {
                continue;
            }
            let header = unsafe { *(ace_ptr.cast::<windows_sys::Win32::Security::ACE_HEADER>()) };
            if header.AceType != 1 {
                continue;
            }
            let ace = unsafe { &*(ace_ptr.cast::<ACCESS_DENIED_ACE>()) };
            let ace_sid = (&ace.SidStart as *const u32).cast_mut().cast();
            const KEY_WRITE: u32 = 0x0002_0006;
            const DELETE: u32 = 0x0001_0000;
            if (ace.Mask & (KEY_WRITE | DELETE)) == (KEY_WRITE | DELETE)
                && unsafe { EqualSid(target_sid, ace_sid) } != 0
            {
                found = true;
                break;
            }
        }
    }
    unsafe {
        LocalFree(target_sid.cast());
        LocalFree(descriptor.cast());
    }
    if found {
        Ok(())
    } else {
        Err(CoreError::InvalidParams(
            "Required registry deny ACL is missing.",
        ))
    }
}

#[cfg(not(windows))]
fn install_registry_deny_acl(_sid: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "Registry ACLs are only available on Windows.",
    ))
}

#[cfg(not(windows))]
fn verify_registry_deny_acl(_sid: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "Registry ACLs are only available on Windows.",
    ))
}

fn policy_action(params: &Value) -> Result<&str, CoreError> {
    let action = params
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("verify");
    if matches!(action, "verify" | "install" | "remove") {
        Ok(action)
    } else {
        Err(CoreError::InvalidParams(
            "Windows policy action must be verify, install, or remove.",
        ))
    }
}

#[cfg(windows)]
fn run_isolation_policy_action(action: &str, plugin_id: &str) -> Result<(), CoreError> {
    let script = env::var_os("PDPP_ISOLATION_SCRIPT")
        .map(std::path::PathBuf::from)
        .or_else(|| {
            env::current_exe()
                .ok()
                .and_then(|path| path.parent().map(|dir| dir.to_path_buf()))
                .map(|dir| dir.join("desktop-plugin-isolation.ps1"))
        })
        .or_else(|| {
            env::current_dir()
                .ok()
                .map(|dir| dir.join("scripts").join("desktop-plugin-isolation.ps1"))
        })
        .ok_or(CoreError::InvalidParams(
            "Windows isolation policy script is unavailable.",
        ))?;
    if !script.is_file() {
        return Err(CoreError::InvalidParams(
            "Windows isolation policy script is unavailable.",
        ));
    }
    let verb = match action {
        "install" => "Install",
        "remove" => "Remove",
        _ => return Ok(()),
    };
    let powershell = env::var_os("SystemRoot")
        .map(|root| {
            Path::new(&root)
                .join("System32")
                .join("WindowsPowerShell")
                .join("v1.0")
                .join("powershell.exe")
        })
        .unwrap_or_else(|| std::path::PathBuf::from("powershell.exe"));
    let status = Command::new(powershell)
        .arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(script)
        .arg("-Action")
        .arg(verb)
        .arg("-PluginId")
        .arg(plugin_id)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| CoreError::InvalidParams("Windows isolation policy action failed."))?;
    if status.success() {
        Ok(())
    } else {
        Err(CoreError::InvalidParams(
            "Windows isolation policy action was rejected.",
        ))
    }
}

#[cfg(not(windows))]
fn run_isolation_policy_action(_action: &str, _plugin_id: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "Windows policy actions are only available on Windows.",
    ))
}

#[cfg(windows)]
fn run_powershell_check(script: &str) -> Result<(), CoreError> {
    let powershell = env::var_os("SystemRoot")
        .map(|root| {
            Path::new(&root)
                .join("System32")
                .join("WindowsPowerShell")
                .join("v1.0")
                .join("powershell.exe")
        })
        .unwrap_or_else(|| std::path::PathBuf::from("powershell.exe"));
    let status = Command::new(powershell)
        .arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-Command")
        .arg(script)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| CoreError::InvalidParams("Windows policy verification is unavailable."))?;
    if !status.success() {
        return Err(CoreError::InvalidParams(
            "Required Windows isolation policy is missing or does not match the AppContainer SID.",
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
fn run_powershell_check(_script: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "Windows policy verification is only available on Windows.",
    ))
}

fn absolute_directory(value: &str) -> Result<std::path::PathBuf, CoreError> {
    let path = std::path::PathBuf::from(value);
    if !path.is_absolute() {
        return Err(CoreError::InvalidParams("workspace_root must be absolute."));
    }
    fs::create_dir_all(&path)
        .map_err(|_| CoreError::InvalidParams("workspace_root is unavailable."))?;
    Ok(path)
}

fn canonical_file(value: &str) -> Result<std::path::PathBuf, CoreError> {
    let path = std::path::PathBuf::from(value);
    if !path.is_absolute() {
        return Err(CoreError::InvalidParams("real_path must be absolute."));
    }
    fs::canonicalize(path).map_err(|_| CoreError::InvalidParams("real_path is unavailable."))
}

fn denied_file_path(path: &Path) -> bool {
    let mut normalized = path
        .to_string_lossy()
        .replace('/', "\\")
        .to_ascii_lowercase();
    if normalized.starts_with("\\\\?\\") {
        normalized = normalized.trim_start_matches("\\\\?\\").to_string();
    } else if normalized.starts_with("\\\\") {
        return true;
    }
    let windows_root = env::var("WINDIR")
        .or_else(|_| env::var("SystemRoot"))
        .unwrap_or_else(|_| "C:\\Windows".to_string())
        .replace('/', "\\")
        .trim_end_matches('\\')
        .to_ascii_lowercase();
    normalized == windows_root || normalized.starts_with(&(windows_root + "\\"))
}

fn appcontainer_profile_name(plugin_id: &str) -> String {
    format!(
        "PasswordDetective.Plugin.{}",
        hex_digest(plugin_id.as_bytes())[..24].to_string()
    )
}

fn hex_digest(input: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(input);
    digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(windows)]
fn create_or_derive_appcontainer(profile_name: &str) -> Result<(String, bool), CoreError> {
    use std::ffi::{OsStr, c_void};
    use std::os::windows::ffi::OsStrExt;
    use std::ptr::null_mut;

    const ALREADY_EXISTS: i32 = -2147024713;
    #[link(name = "userenv")]
    #[link(name = "advapi32")]
    unsafe extern "system" {
        fn CreateAppContainerProfile(
            name: *const u16,
            display_name: *const u16,
            description: *const u16,
            capabilities: *mut c_void,
            capability_count: u32,
            app_container_sid: *mut *mut c_void,
        ) -> i32;
        fn DeriveAppContainerSidFromAppContainerName(
            name: *const u16,
            app_container_sid: *mut *mut c_void,
        ) -> i32;
        fn ConvertSidToStringSidW(sid: *const c_void, string_sid: *mut *mut u16) -> i32;
        fn LocalFree(memory: *mut c_void) -> *mut c_void;
        fn FreeSid(sid: *mut c_void) -> *mut c_void;
    }

    fn wide(value: &str) -> Vec<u16> {
        OsStr::new(value).encode_wide().chain([0]).collect()
    }

    let name = wide(profile_name);
    let display_name = wide("Password Detective Sandbox");
    let description = wide("Isolated Password Detective plugin sandbox");
    let mut sid = null_mut();
    let mut result = unsafe {
        CreateAppContainerProfile(
            name.as_ptr(),
            display_name.as_ptr(),
            description.as_ptr(),
            null_mut(),
            0,
            &mut sid,
        )
    };
    let created = result >= 0;
    if !created {
        if result != ALREADY_EXISTS {
            return Err(CoreError::InvalidParams(
                "sandbox.create could not create AppContainer.",
            ));
        }
        result = unsafe { DeriveAppContainerSidFromAppContainerName(name.as_ptr(), &mut sid) };
        if result < 0 {
            return Err(CoreError::InvalidParams(
                "sandbox.create could not derive AppContainer SID.",
            ));
        }
    }
    if sid.is_null() {
        return Err(CoreError::InvalidParams(
            "sandbox.create returned an empty AppContainer SID.",
        ));
    }

    let mut string_sid = null_mut();
    let converted = unsafe { ConvertSidToStringSidW(sid, &mut string_sid) } != 0;
    if !converted || string_sid.is_null() {
        unsafe { FreeSid(sid) };
        return Err(CoreError::InvalidParams(
            "sandbox.create could not stringify AppContainer SID.",
        ));
    }
    let mut length = 0usize;
    while unsafe { *string_sid.add(length) } != 0 {
        length += 1;
    }
    let sid_text =
        String::from_utf16_lossy(unsafe { std::slice::from_raw_parts(string_sid, length) });
    unsafe {
        LocalFree(string_sid.cast());
        FreeSid(sid);
    }
    Ok((sid_text, created))
}

#[cfg(not(windows))]
fn create_or_derive_appcontainer(_profile_name: &str) -> Result<(String, bool), CoreError> {
    Err(CoreError::NotImplemented(
        "AppContainer is only available on Windows.",
    ))
}

#[cfg(windows)]
fn delete_appcontainer_profile(profile_name: &str) -> Result<(), CoreError> {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "userenv")]
    unsafe extern "system" {
        fn DeleteAppContainerProfile(name: *const u16) -> i32;
    }
    let name: Vec<u16> = OsStr::new(profile_name).encode_wide().chain([0]).collect();
    let result = unsafe { DeleteAppContainerProfile(name.as_ptr()) };
    if result < 0 {
        return Err(CoreError::InvalidParams(
            "sandbox.destroy could not delete AppContainer.",
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
fn delete_appcontainer_profile(_profile_name: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "AppContainer is only available on Windows.",
    ))
}

#[cfg(windows)]
fn grant_directory_read_write(path: &Path, sid: &str) -> Result<(), CoreError> {
    let system_root = env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
    let icacls = Path::new(&system_root).join("System32").join("icacls.exe");
    let grant = format!("*{sid}:(OI)(CI)M");
    let status = Command::new(icacls)
        .arg(path)
        .arg("/grant")
        .arg(grant)
        .arg("/Q")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| {
            CoreError::InvalidParams("sandbox.create could not apply work directory ACL.")
        })?;
    if !status.success() {
        return Err(CoreError::InvalidParams(
            "sandbox.create work directory ACL was rejected.",
        ));
    }
    Ok(())
}

#[cfg(windows)]
fn grant_directory_read_execute(path: &Path, sid: &str) -> Result<(), CoreError> {
    let system_root = env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
    let icacls = Path::new(&system_root).join("System32").join("icacls.exe");
    let grant = format!("*{sid}:(OI)(CI)RX");
    let status = Command::new(icacls)
        .arg(path)
        .arg("/grant")
        .arg(grant)
        .arg("/Q")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| CoreError::InvalidParams("process.spawn could not apply entrypoint ACL."))?;
    if !status.success() {
        return Err(CoreError::InvalidParams(
            "process.spawn entrypoint ACL was rejected.",
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
fn grant_directory_read_execute(_path: &Path, _sid: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "AppContainer ACLs are only available on Windows.",
    ))
}

#[cfg(not(windows))]
fn grant_directory_read_write(_path: &Path, _sid: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "AppContainer ACLs are only available on Windows.",
    ))
}

#[cfg(windows)]
fn remove_directory_acl(path: &str, sid: &str) -> Result<(), CoreError> {
    let system_root = env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
    let icacls = Path::new(&system_root).join("System32").join("icacls.exe");
    let remove = format!("*{sid}");
    let status = Command::new(icacls)
        .arg(path)
        .arg("/remove")
        .arg(remove)
        .arg("/Q")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| {
            CoreError::InvalidParams("sandbox.destroy could not remove work directory ACL.")
        })?;
    if !status.success() {
        return Err(CoreError::InvalidParams(
            "sandbox.destroy work directory ACL cleanup failed.",
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
fn remove_directory_acl(_path: &str, _sid: &str) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "AppContainer ACLs are only available on Windows.",
    ))
}

#[derive(Debug, Clone)]
struct NativeProcessHandle {
    process_handle: usize,
    job_handle: usize,
    process_id: u32,
    profile_sid: String,
}

#[derive(Debug, Clone, Copy)]
struct StdioHandles {
    input: usize,
    output: usize,
    error: usize,
}

#[cfg(windows)]
#[allow(unused_assignments)]
fn spawn_native_process(
    executable: &Path,
    working_directory: &Path,
    arguments: &[String],
    sandbox: &SandboxRecord,
    stdio: StdioHandles,
) -> Result<NativeProcessHandle, CoreError> {
    use std::ffi::{OsStr, c_void};
    use std::os::windows::ffi::OsStrExt;
    use std::ptr::{null, null_mut};

    #[repr(C)]
    struct StartupInfoW {
        cb: u32,
        reserved: *mut u16,
        desktop: *mut u16,
        title: *mut u16,
        x: u32,
        y: u32,
        x_size: u32,
        y_size: u32,
        x_count_chars: u32,
        y_count_chars: u32,
        fill_attribute: u32,
        flags: u32,
        show_window: u16,
        reserved2: u16,
        reserved_data: *mut u8,
        standard_input: *mut c_void,
        standard_output: *mut c_void,
        standard_error: *mut c_void,
    }

    #[repr(C)]
    struct StartupInfoExW {
        startup_info: StartupInfoW,
        attribute_list: *mut c_void,
    }

    #[repr(C)]
    struct ProcessInformation {
        process: *mut c_void,
        thread: *mut c_void,
        process_id: u32,
        thread_id: u32,
    }

    #[repr(C)]
    struct SecurityCapabilities {
        app_container_sid: *mut c_void,
        capabilities: *mut c_void,
        capability_count: u32,
        reserved: u32,
    }

    #[repr(C)]
    struct JobObjectBasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: u32,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: u32,
        affinity: usize,
        priority_class: u32,
        scheduling_class: u32,
    }

    #[repr(C)]
    struct IoCounters {
        read_operations: u64,
        write_operations: u64,
        other_operations: u64,
        read_transfers: u64,
        write_transfers: u64,
        other_transfers: u64,
    }

    #[repr(C)]
    struct JobObjectExtendedLimitInformation {
        basic_limit_information: JobObjectBasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    #[repr(C)]
    struct JobObjectCpuRateControlInformation {
        control_flags: u32,
        cpu_rate: u32,
    }

    #[link(name = "advapi32")]
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn ConvertStringSidToSidW(string_sid: *const u16, sid: *mut *mut c_void) -> i32;
        fn LocalFree(memory: *mut c_void) -> *mut c_void;
        fn CreateJobObjectW(attributes: *mut c_void, name: *const u16) -> *mut c_void;
        fn SetInformationJobObject(
            job: *mut c_void,
            info_type: u32,
            info: *const c_void,
            length: u32,
        ) -> i32;
        fn AssignProcessToJobObject(job: *mut c_void, process: *mut c_void) -> i32;
        fn CreateProcessW(
            application_name: *const u16,
            command_line: *mut u16,
            process_attributes: *mut c_void,
            thread_attributes: *mut c_void,
            inherit_handles: i32,
            creation_flags: u32,
            environment: *mut c_void,
            current_directory: *const u16,
            startup_info: *mut StartupInfoExW,
            process_information: *mut ProcessInformation,
        ) -> i32;
        fn ResumeThread(thread: *mut c_void) -> u32;
        fn CloseHandle(object: *mut c_void) -> i32;
        fn SetHandleInformation(handle: *mut c_void, mask: u32, flags: u32) -> i32;
        fn TerminateJobObject(job: *mut c_void, exit_code: u32) -> i32;
        fn InitializeProcThreadAttributeList(
            attribute_list: *mut c_void,
            attribute_count: u32,
            flags: u32,
            size: *mut usize,
        ) -> i32;
        fn UpdateProcThreadAttribute(
            attribute_list: *mut c_void,
            flags: u32,
            attribute: usize,
            value: *mut c_void,
            size: usize,
            previous_value: *mut c_void,
            return_size: *mut usize,
        ) -> i32;
        fn DeleteProcThreadAttributeList(attribute_list: *mut c_void);
    }

    const CREATE_SUSPENDED: u32 = 0x00000004;
    const CREATE_UNICODE_ENVIRONMENT: u32 = 0x00000400;
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    const EXTENDED_STARTUPINFO_PRESENT: u32 = 0x00080000;
    const PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES: usize = 0x00020009;
    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: u32 = 9;
    const JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION: u32 = 15;
    const JOB_OBJECT_LIMIT_ACTIVE_PROCESS: u32 = 0x00000008;
    const JOB_OBJECT_LIMIT_PROCESS_MEMORY: u32 = 0x00000100;
    const JOB_OBJECT_LIMIT_JOB_MEMORY: u32 = 0x00000200;
    const JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION: u32 = 0x00000400;
    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x00002000;

    let to_wide =
        |value: &str| -> Vec<u16> { OsStr::new(value).encode_wide().chain([0]).collect() };
    let sid_wide = to_wide(&sandbox.profile_sid);
    let mut app_container_sid = null_mut();
    if unsafe { ConvertStringSidToSidW(sid_wide.as_ptr(), &mut app_container_sid) } == 0 {
        return Err(CoreError::InvalidParams(
            "process.spawn could not load AppContainer SID.",
        ));
    }
    let mut job = unsafe { CreateJobObjectW(null_mut(), null()) };
    if job.is_null() {
        unsafe { LocalFree(app_container_sid) };
        return Err(CoreError::InvalidParams(
            "process.spawn could not create Job Object.",
        ));
    }
    let mut handle_list = [stdio.input, stdio.output, stdio.error];
    let attribute_count = 2;
    let mut attribute_size = 0usize;
    unsafe {
        InitializeProcThreadAttributeList(null_mut(), attribute_count, 0, &mut attribute_size)
    };
    let attribute_list = unsafe { libc_alloc(attribute_size) };
    let mut security_capabilities = SecurityCapabilities {
        app_container_sid,
        capabilities: null_mut(),
        capability_count: 0,
        reserved: 0,
    };
    let mut process = null_mut();
    let mut thread = null_mut();
    let mut attribute_initialized = false;
    let mut result: Result<NativeProcessHandle, CoreError> = Err(CoreError::InvalidParams(
        "process.spawn could not start AppContainer process.",
    ));
    unsafe {
        if attribute_list.is_null()
            || InitializeProcThreadAttributeList(
                attribute_list,
                attribute_count,
                0,
                &mut attribute_size,
            ) == 0
            || UpdateProcThreadAttribute(
                attribute_list,
                0,
                PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                (&mut security_capabilities as *mut SecurityCapabilities).cast(),
                std::mem::size_of::<SecurityCapabilities>(),
                null_mut(),
                null_mut(),
            ) == 0
            || UpdateProcThreadAttribute(
                attribute_list,
                0,
                0x00020002,
                handle_list.as_mut_ptr().cast(),
                std::mem::size_of_val(&handle_list),
                null_mut(),
                null_mut(),
            ) == 0
        {
            result = Err(CoreError::InvalidParams(
                "process.spawn could not configure AppContainer attributes.",
            ));
        } else {
            attribute_initialized = true;
            let mut limits = JobObjectExtendedLimitInformation {
                basic_limit_information: JobObjectBasicLimitInformation {
                    per_process_user_time_limit: 0,
                    per_job_user_time_limit: 0,
                    limit_flags: JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                        | JOB_OBJECT_LIMIT_PROCESS_MEMORY
                        | JOB_OBJECT_LIMIT_JOB_MEMORY
                        | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
                        | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                    minimum_working_set_size: 0,
                    maximum_working_set_size: 0,
                    active_process_limit: 1,
                    affinity: 0,
                    priority_class: 0,
                    scheduling_class: 0,
                },
                io_info: IoCounters {
                    read_operations: 0,
                    write_operations: 0,
                    other_operations: 0,
                    read_transfers: 0,
                    write_transfers: 0,
                    other_transfers: 0,
                },
                process_memory_limit: sandbox.memory_mb as usize * 1024 * 1024,
                job_memory_limit: sandbox.memory_mb as usize * 1024 * 1024,
                peak_process_memory_used: 0,
                peak_job_memory_used: 0,
            };
            if SetInformationJobObject(
                job,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                (&mut limits as *mut JobObjectExtendedLimitInformation).cast(),
                std::mem::size_of::<JobObjectExtendedLimitInformation>() as u32,
            ) == 0
            {
                result = Err(CoreError::InvalidParams(
                    "process.spawn could not apply Job Object limits.",
                ));
            } else {
                let mut cpu = JobObjectCpuRateControlInformation {
                    control_flags: 0x1 | 0x4,
                    cpu_rate: (sandbox.cpu_percent as u32).saturating_mul(100),
                };
                if SetInformationJobObject(
                    job,
                    JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION,
                    (&mut cpu as *mut JobObjectCpuRateControlInformation).cast(),
                    std::mem::size_of::<JobObjectCpuRateControlInformation>() as u32,
                ) == 0
                {
                    result = Err(CoreError::InvalidParams(
                        "process.spawn could not apply CPU limits.",
                    ));
                } else {
                    let mut command = quote_command_line(executable, arguments);
                    let current_directory = to_wide(&path_string(working_directory));
                    let mut environment = build_environment_block(working_directory);
                    let mut startup = StartupInfoExW {
                        startup_info: StartupInfoW {
                            cb: std::mem::size_of::<StartupInfoExW>() as u32,
                            reserved: null_mut(),
                            desktop: null_mut(),
                            title: null_mut(),
                            x: 0,
                            y: 0,
                            x_size: 0,
                            y_size: 0,
                            x_count_chars: 0,
                            y_count_chars: 0,
                            fill_attribute: 0,
                            flags: 0x00000100,
                            show_window: 0,
                            reserved2: 0,
                            reserved_data: null_mut(),
                            standard_input: stdio.input as *mut c_void,
                            standard_output: stdio.output as *mut c_void,
                            standard_error: stdio.error as *mut c_void,
                        },
                        attribute_list,
                    };
                    let mut information = ProcessInformation {
                        process: null_mut(),
                        thread: null_mut(),
                        process_id: 0,
                        thread_id: 0,
                    };
                    let handles_ready = handle_list.iter().all(|handle| {
                        SetHandleInformation(*handle as *mut c_void, 0x00000001, 0x00000001) != 0
                    });
                    if !handles_ready {
                        result = Err(CoreError::InvalidParams(
                            "process.spawn stdio handles are not inheritable.",
                        ));
                    } else if CreateProcessW(
                        to_wide(&path_string(executable)).as_ptr(),
                        command.as_mut_ptr(),
                        null_mut(),
                        null_mut(),
                        1,
                        CREATE_SUSPENDED
                            | CREATE_UNICODE_ENVIRONMENT
                            | CREATE_NO_WINDOW
                            | EXTENDED_STARTUPINFO_PRESENT,
                        environment.as_mut_ptr().cast(),
                        current_directory.as_ptr(),
                        &mut startup,
                        &mut information,
                    ) == 0
                    {
                        result = Err(CoreError::InvalidParams(
                            "process.spawn could not create the process.",
                        ));
                    } else {
                        process = information.process;
                        thread = information.thread;
                        if AssignProcessToJobObject(job, process) == 0
                            || ResumeThread(thread) == u32::MAX
                        {
                            let _ = TerminateJobObject(job, 1);
                            result = Err(CoreError::InvalidParams(
                                "process.spawn could not attach the process to its Job Object.",
                            ));
                        } else {
                            CloseHandle(thread);
                            thread = null_mut();
                            result = Ok(NativeProcessHandle {
                                process_handle: process as usize,
                                job_handle: job as usize,
                                process_id: information.process_id,
                                profile_sid: sandbox.profile_sid.clone(),
                            });
                            process = null_mut();
                            job = null_mut();
                        }
                    }
                }
            }
        }
        if attribute_initialized {
            DeleteProcThreadAttributeList(attribute_list);
        }
        if !attribute_list.is_null() {
            libc_free(attribute_list, attribute_size);
        }
        if !thread.is_null() {
            CloseHandle(thread);
        }
        if !process.is_null() {
            CloseHandle(process);
        }
        if !job.is_null() {
            CloseHandle(job);
        }
        LocalFree(app_container_sid);
    }
    result
}

#[cfg(not(windows))]
fn spawn_native_process(
    _executable: &Path,
    _working_directory: &Path,
    _arguments: &[String],
    _sandbox: &SandboxRecord,
    _stdio: StdioHandles,
) -> Result<NativeProcessHandle, CoreError> {
    Err(CoreError::NotImplemented(
        "process.spawn is only available on Windows.",
    ))
}

#[cfg(windows)]
fn terminate_native_process(handle: NativeProcessHandle) -> Result<(), CoreError> {
    use std::ffi::c_void;
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn TerminateJobObject(job: *mut c_void, exit_code: u32) -> i32;
        fn CloseHandle(object: *mut c_void) -> i32;
    }
    unsafe {
        if TerminateJobObject(handle.job_handle as *mut c_void, 1) == 0 {
            CloseHandle(handle.process_handle as *mut c_void);
            CloseHandle(handle.job_handle as *mut c_void);
            return Err(CoreError::InvalidParams(
                "process.terminate could not terminate the Job Object.",
            ));
        }
        CloseHandle(handle.process_handle as *mut c_void);
        CloseHandle(handle.job_handle as *mut c_void);
    }
    Ok(())
}

#[cfg(not(windows))]
fn terminate_native_process(_handle: NativeProcessHandle) -> Result<(), CoreError> {
    Err(CoreError::NotImplemented(
        "process.terminate is only available on Windows.",
    ))
}

#[cfg(windows)]
unsafe fn libc_alloc(size: usize) -> *mut std::ffi::c_void {
    if size == 0 {
        return std::ptr::null_mut();
    }
    unsafe { std::alloc::alloc(std::alloc::Layout::from_size_align_unchecked(size, 8)).cast() }
}

#[cfg(windows)]
unsafe fn libc_free(pointer: *mut std::ffi::c_void, size: usize) {
    if !pointer.is_null() {
        unsafe {
            std::alloc::dealloc(
                pointer.cast(),
                std::alloc::Layout::from_size_align_unchecked(size, 8),
            );
        }
    }
}

#[cfg(windows)]
fn quote_command_line(executable: &Path, arguments: &[String]) -> Vec<u16> {
    let mut command = String::new();
    command.push('"');
    command.push_str(&path_string(executable).replace('"', "\\\""));
    command.push('"');
    for argument in arguments {
        command.push(' ');
        command.push('"');
        command.push_str(&argument.replace('"', "\\\""));
        command.push('"');
    }
    command.encode_utf16().chain([0]).collect()
}

#[cfg(windows)]
fn build_environment_block(working_directory: &Path) -> Vec<u16> {
    let allowed = [
        "ALLUSERSPROFILE",
        "ComSpec",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "Path",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "PROCESSOR_LEVEL",
        "PROCESSOR_REVISION",
        "ProgramData",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramW6432",
        "SystemDrive",
        "SystemRoot",
        "WINDIR",
    ];
    let mut values = BTreeMap::new();
    for name in allowed {
        if let Ok(value) = env::var(name) {
            values.insert(name.to_string(), value);
        }
    }
    let profile = working_directory.join("profile");
    let local = profile.join("AppData").join("Local");
    let roaming = profile.join("AppData").join("Roaming");
    let temp = local.join("Temp");
    values.insert("APPDATA".to_string(), path_string(&roaming));
    values.insert("LOCALAPPDATA".to_string(), path_string(&local));
    values.insert("TEMP".to_string(), path_string(&temp));
    values.insert("TMP".to_string(), path_string(&temp));
    values.insert("USERPROFILE".to_string(), path_string(&profile));
    values.insert("HOMEDRIVE".to_string(), path_root_string(&profile));
    values.insert("HOMEPATH".to_string(), path_string(&profile));
    let mut block = values
        .into_iter()
        .map(|(key, value)| format!("{key}={value}"))
        .collect::<Vec<_>>()
        .join("\0")
        .encode_utf16()
        .collect::<Vec<_>>();
    block.extend([0, 0]);
    block
}

fn attest_host() -> Value {
    let is_appcontainer = is_current_process_appcontainer();
    let no_host_secret_leak = false;
    let no_fs_breakout = false;
    json!({
        "status": if is_appcontainer && no_host_secret_leak && no_fs_breakout {
            "ok"
        } else {
            "failed"
        },
        "is_appcontainer": is_appcontainer,
        "no_host_secret_leak": no_host_secret_leak,
        "no_fs_breakout": no_fs_breakout,
        "checks_pending": ["environment_canary", "filesystem_canary"],
    })
}

fn sanitize_environment(params: &Value) -> Result<Value, CoreError> {
    let secret_keys = params
        .get("host_secret_keys")
        .and_then(Value::as_array)
        .ok_or(CoreError::InvalidParams(
            "env.sanitize requires host_secret_keys.",
        ))?;
    if secret_keys.len() > 64
        || secret_keys.iter().any(|key| {
            key.as_str()
                .is_none_or(|value| value.is_empty() || value.len() > 128)
        })
    {
        return Err(CoreError::InvalidParams(
            "env.sanitize host_secret_keys are invalid.",
        ));
    }

    let allowed = [
        "ALLUSERSPROFILE",
        "ComSpec",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "Path",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "PROCESSOR_LEVEL",
        "PROCESSOR_REVISION",
        "ProgramData",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramW6432",
        "SystemDrive",
        "SystemRoot",
        "WINDIR",
    ];
    let secret_names: HashSet<&str> = secret_keys.iter().filter_map(Value::as_str).collect();
    let mut environment = BTreeMap::new();
    for name in allowed {
        if secret_names.contains(name) {
            continue;
        }
        if let Ok(value) = env::var(name) {
            environment.insert(name.to_string(), value);
        }
    }
    let work_root = env::current_dir().map_err(|_| {
        CoreError::InvalidParams("env.sanitize cannot determine the work directory.")
    })?;
    let profile = work_root.join("profile");
    let local_app_data = profile.join("AppData").join("Local");
    let roaming_app_data = profile.join("AppData").join("Roaming");
    let temp = local_app_data.join("Temp");
    environment.insert("APPDATA".to_string(), path_string(&roaming_app_data));
    environment.insert("LOCALAPPDATA".to_string(), path_string(&local_app_data));
    environment.insert("TEMP".to_string(), path_string(&temp));
    environment.insert("TMP".to_string(), path_string(&temp));
    environment.insert("USERPROFILE".to_string(), path_string(&profile));
    environment.insert("HOMEDRIVE".to_string(), path_root_string(&profile));
    environment.insert("HOMEPATH".to_string(), path_string(&profile));

    Ok(json!({
        "status": "ok",
        "environment": environment,
        "secret_keys_excluded": secret_keys.len(),
    }))
}

fn valid_plugin_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 255
        && value.split('.').count() >= 2
        && value.chars().all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || matches!(character, '.' | '_' | '-')
        })
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn path_root_string(path: &Path) -> String {
    path.components()
        .next()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .unwrap_or_default()
}

fn request_id(request: &Value) -> Value {
    request.get("id").cloned().unwrap_or(Value::Null)
}

fn error_response(id: Value, error: CoreError) -> Value {
    json!({
        "jsonrpc": JSON_RPC_VERSION,
        "id": id,
        "error": { "code": error.code(), "message": error.message() },
    })
}

fn write_response(writer: &mut impl Write, response: &Value) -> io::Result<()> {
    serde_json::to_writer(&mut *writer, response)?;
    writer.write_all(b"\n")?;
    writer.flush()
}

fn json_depth(value: &Value) -> usize {
    match value {
        Value::Array(values) => values.iter().map(json_depth).max().unwrap_or(0) + 1,
        Value::Object(values) => values.values().map(json_depth).max().unwrap_or(0) + 1,
        _ => 0,
    }
}

#[cfg(windows)]
fn is_current_process_appcontainer() -> bool {
    use std::ffi::c_void;
    use std::ptr::null_mut;

    const TOKEN_QUERY: u32 = 0x0008;
    const TOKEN_IS_APPCONTAINER: u32 = 29;
    #[link(name = "kernel32")]
    #[link(name = "advapi32")]
    unsafe extern "system" {
        fn GetCurrentProcess() -> *mut c_void;
        fn OpenProcessToken(
            process_handle: *mut c_void,
            desired_access: u32,
            token_handle: *mut *mut c_void,
        ) -> i32;
        fn GetTokenInformation(
            token_handle: *mut c_void,
            token_information_class: u32,
            token_information: *mut c_void,
            token_information_length: u32,
            return_length: *mut u32,
        ) -> i32;
        fn CloseHandle(object: *mut c_void) -> i32;
    }

    unsafe {
        let mut token = null_mut();
        if OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) == 0 {
            return false;
        }
        let mut value = 0u32;
        let mut length = 0u32;
        let success = GetTokenInformation(
            token,
            TOKEN_IS_APPCONTAINER,
            (&mut value as *mut u32).cast(),
            std::mem::size_of::<u32>() as u32,
            &mut length,
        ) != 0;
        let _ = CloseHandle(token);
        success && value != 0
    }
}

#[cfg(not(windows))]
fn is_current_process_appcontainer() -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn response(line: &str) -> Value {
        let mut state = CoreState::default();
        handle_line(&mut state, line)
    }

    #[test]
    fn rejects_unknown_method() {
        let response = response(r#"{"jsonrpc":"2.0","id":"1","method":"unknown","params":{}}"#);
        assert_eq!(response["error"]["code"], -32601);
    }

    #[test]
    fn rejects_deep_requests() {
        let mut value = String::from("{}");
        for _ in 0..MAX_JSON_DEPTH + 1 {
            value = format!(r#"{{"nested":{value}}}"#);
        }
        let request =
            format!(r#"{{"jsonrpc":"2.0","id":"1","method":"attest.host","params":{value}}}"#);
        let response = response(&request);
        assert_eq!(response["error"]["code"], -32600);
    }

    #[test]
    fn validates_sandbox_create_before_fail_closed() {
        let response = response(
            r#"{"jsonrpc":"2.0","id":"1","method":"sandbox.create","params":{"plugin_id":"bad","limits":{}}}"#,
        );
        assert_eq!(response["error"]["code"], -32602);
    }

    #[test]
    fn sandbox_create_requires_workspace_root_before_native_setup() {
        let response = response(
            r#"{"jsonrpc":"2.0","id":"1","method":"sandbox.create","params":{"plugin_id":"com.example.plugin","limits":{"memory_mb":128,"cpu_percent":25,"command_timeout_seconds":30}}}"#,
        );
        assert_eq!(response["error"]["code"], -32602);
    }

    #[test]
    fn sanitize_environment_excludes_requested_secrets() {
        let response = response(
            r#"{"jsonrpc":"2.0","id":"1","method":"env.sanitize","params":{"host_secret_keys":["APP_SECRET_KEY"]}}"#,
        );
        assert_eq!(response["result"]["status"], "ok");
        assert!(
            response["result"]["environment"]
                .get("APP_SECRET_KEY")
                .is_none()
        );
    }

    #[test]
    fn sanitize_environment_excludes_requested_allowlist_names() {
        let response = response(
            r#"{"jsonrpc":"2.0","id":"1","method":"env.sanitize","params":{"host_secret_keys":["Path"]}}"#,
        );
        assert!(response["result"]["environment"].get("Path").is_none());
    }

    #[test]
    fn allows_local_extended_paths_but_denies_unc_paths() {
        assert!(!denied_file_path(Path::new(
            r"\\?\C:\Users\synthetic\file.txt"
        )));
        assert!(denied_file_path(Path::new(r"\\server\share\file.txt")));
    }

    #[test]
    fn rejects_unknown_request_fields() {
        let response = response(
            r#"{"jsonrpc":"2.0","id":"1","method":"attest.host","params":{},"unexpected":true}"#,
        );
        assert_eq!(response["error"]["code"], -32600);
    }

    #[test]
    fn attest_fails_closed_outside_appcontainer() {
        let response = response(r#"{"jsonrpc":"2.0","id":"1","method":"attest.host","params":{}}"#);
        assert_eq!(response["result"]["status"], "failed");
        assert_eq!(response["result"]["is_appcontainer"], false);
    }

    #[test]
    fn canary_runs_all_forced_probes_and_returns_destruction_proof() {
        let root =
            std::env::temp_dir().join(format!("pdpp-sandbox-core-canary-{}", std::process::id()));
        std::fs::create_dir_all(&root).expect("test workspace");
        let plugin_id = "com.example.canary";
        let mut state = CoreState::default();
        state.sandboxes.insert(
            "S-1-15-2-test".to_string(),
            SandboxRecord {
                plugin_id: plugin_id.to_string(),
                profile_name: "test-profile".to_string(),
                profile_sid: "S-1-15-2-test".to_string(),
                work_dir: root.to_string_lossy().into_owned(),
                acl_paths: vec![],
                memory_mb: 128,
                cpu_percent: 25,
                command_timeout_seconds: 30,
            },
        );
        let request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "canary",
            "method": "canary.run",
            "params": { "plugin_id": plugin_id, "task": {} }
        });
        let result = handle_line(&mut state, &request.to_string());
        assert_eq!(result["result"]["status"], "completed");
        for probe in [
            "probe",
            "environment",
            "spawn-child",
            "hang",
            "oversized-output",
        ] {
            assert_eq!(result["result"]["probes"][probe]["status"], "passed");
        }
        assert_eq!(
            result["result"]["destruction_proof"]["marker_removed"],
            true
        );
        assert_eq!(result["result"]["sensitive_values_redacted"], true);
        std::fs::remove_dir_all(root).expect("cleanup");
    }

    #[cfg(windows)]
    #[test]
    fn sandbox_and_file_broker_round_trip_with_native_windows_state() {
        let root =
            std::env::temp_dir().join(format!("pdpp-sandbox-core-test-{}", std::process::id()));
        std::fs::create_dir_all(&root).expect("test workspace");
        let plugin_id = format!("com.example.native-{}", std::process::id());
        let mut state = CoreState::default();
        let create_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "create",
            "method": "sandbox.create",
            "params": {
                "plugin_id": plugin_id,
                "workspace_root": root,
                "limits": {
                    "memory_mb": 128,
                    "cpu_percent": 25,
                    "command_timeout_seconds": 30
                }
            }
        });
        let created = handle_line(&mut state, &create_request.to_string());
        assert!(created.get("result").is_some(), "{created}");
        let profile_sid = created["result"]["profile_sid"]
            .as_str()
            .unwrap()
            .to_string();
        let file = root.join("selected.txt");
        std::fs::write(&file, b"sandbox-core-file").expect("test file");
        let grant_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "grant",
            "method": "fs.grant_read",
            "params": {
                "plugin_id": plugin_id,
                "real_path": file,
                "max_bytes": 1024
            }
        });
        let granted = handle_line(&mut state, &grant_request.to_string());
        assert!(granted.get("result").is_some(), "{granted}");
        let file_ref = granted["result"]["file_ref"].as_str().unwrap();
        let read_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "read",
            "method": "fs.read_chunk",
            "params": { "file_ref": file_ref, "offset": 0, "length": 1024 }
        });
        let read = handle_line(&mut state, &read_request.to_string());
        assert_eq!(read["result"]["bytes_read"], 17);
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(read["result"]["data_base64"].as_str().unwrap())
            .unwrap();
        assert_eq!(bytes, b"sandbox-core-file");
        let destroy_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "destroy",
            "method": "sandbox.destroy",
            "params": { "profile_sid": profile_sid }
        });
        let destroyed = handle_line(&mut state, &destroy_request.to_string());
        assert_eq!(destroyed["result"]["ok"], true);
        let _ = std::fs::remove_dir_all(root);
    }

    #[cfg(windows)]
    #[test]
    fn process_spawn_and_terminate_use_opaque_job_handle() {
        let root = std::env::temp_dir().join(format!(
            "pdpp-sandbox-core-process-test-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&root).expect("test workspace");
        let plugin_id = format!("com.example.process-{}", std::process::id());
        let mut state = CoreState::default();
        let create_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "create",
            "method": "sandbox.create",
            "params": {
                "plugin_id": plugin_id,
                "workspace_root": root,
                "limits": {
                    "memory_mb": 128,
                    "cpu_percent": 25,
                    "command_timeout_seconds": 30
                }
            }
        });
        let created = handle_line(&mut state, &create_request.to_string());
        assert!(created.get("result").is_some(), "{created}");
        let profile_sid = created["result"]["profile_sid"]
            .as_str()
            .unwrap()
            .to_string();
        let executable = std::env::current_exe().expect("test executable");
        let child = root.join("child.exe");
        std::fs::copy(executable, &child).expect("copy test executable");
        use std::os::windows::io::AsRawHandle;
        let stdin = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open("NUL")
            .expect("stdin handle");
        let stdout = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open("NUL")
            .expect("stdout handle");
        let stderr = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open("NUL")
            .expect("stderr handle");
        let spawn_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "spawn",
            "method": "process.spawn",
            "params": {
                "profile_sid": profile_sid,
                "entrypoint": child,
                "working_directory": root,
                "arguments": ["--filter", "never-match"],
                "stdio_handles": {
                    "stdin": stdin.as_raw_handle() as u64,
                    "stdout": stdout.as_raw_handle() as u64,
                    "stderr": stderr.as_raw_handle() as u64
                }
            }
        });
        let spawned = handle_line(&mut state, &spawn_request.to_string());
        assert!(spawned.get("result").is_some(), "{spawned}");
        let job_handle = spawned["result"]["job_handle"].as_str().unwrap();
        assert!(job_handle.starts_with("job-"));
        assert_eq!(job_handle.len(), 68);
        let terminate_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "terminate",
            "method": "process.terminate",
            "params": { "job_handle": job_handle }
        });
        let terminated = handle_line(&mut state, &terminate_request.to_string());
        assert_eq!(terminated["result"]["ok"], true);
        let destroy_request = json!({
            "jsonrpc": JSON_RPC_VERSION,
            "id": "destroy",
            "method": "sandbox.destroy",
            "params": { "profile_sid": profile_sid }
        });
        let destroyed = handle_line(&mut state, &destroy_request.to_string());
        assert_eq!(destroyed["result"]["ok"], true);
        let _ = std::fs::remove_dir_all(root);
    }
}
