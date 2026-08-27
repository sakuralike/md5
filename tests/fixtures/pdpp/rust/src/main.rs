use serde::Deserialize;
use serde_json::{Value, json};
use std::io::{self, BufRead, Write};

#[derive(Deserialize)]
struct Request {
    id: String,
    method: String,
    params: Value,
}

fn main() {
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout().lock());

    for line in stdin.lock().lines() {
        let Ok(line) = line else { return };
        let Ok(request) = serde_json::from_str::<Request>(&line) else {
            continue;
        };

        let response = match request.method.as_str() {
            "initialize" => json!({
                "jsonrpc": "2.0",
                "id": request.id,
                "result": {
                    "protocol_version": "1.0",
                    "plugin_id": request.params["plugin_id"],
                    "plugin_version": "1.0.0",
                    "capabilities": ["command.echo"]
                }
            }),
            "health/check" => json!({
                "jsonrpc": "2.0",
                "id": request.id,
                "result": { "status": "healthy" }
            }),
            "lifecycle/migrate" => json!({
                "jsonrpc": "2.0",
                "id": request.id,
                "result": { "status": "not_required", "steps": [] }
            }),
            "command/execute" if request.params["command"] == "echo" => json!({
                "jsonrpc": "2.0",
                "id": request.id,
                "result": {
                    "output": request.params["input"],
                    "language": "rust"
                }
            }),
            "shutdown" => {
                let response = json!({
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "result": { "stopped": true }
                });
                write_response(&mut stdout, &response);
                return;
            }
            _ => json!({
                "jsonrpc": "2.0",
                "id": request.id,
                "error": { "code": -32601, "message": "Method not found" }
            }),
        };

        write_response(&mut stdout, &response);
    }
}

fn write_response(stdout: &mut impl Write, response: &Value) {
    if serde_json::to_writer(&mut *stdout, response).is_err() {
        return;
    }
    if stdout.write_all(b"\n").is_err() {
        return;
    }
    let _ = stdout.flush();
}
