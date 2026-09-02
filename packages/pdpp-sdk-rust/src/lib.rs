use base64::Engine;
use serde::de::DeserializeOwned;
use serde::Serialize;
use serde_json::{json, Value};
use std::io::{self, BufRead, Write};

pub struct Client<R: BufRead, W: Write> {
    input: R,
    output: W,
    next_id: u64,
}

impl<R: BufRead, W: Write> Client<R, W> {
    pub fn new(input: R, output: W) -> Self { Self { input, output, next_id: 0 } }

    pub fn call<T: Serialize, O: DeserializeOwned>(&mut self, method: &str, params: T) -> io::Result<O> {
        self.next_id += 1;
        let id = format!("plugin-host-{}", self.next_id);
        let request = json!({"jsonrpc":"2.0","id":id,"method":method,"params":params});
        let line = serde_json::to_vec(&request).map_err(io::Error::other)?;
        if line.len() > 1024 * 1024 { return Err(io::Error::new(io::ErrorKind::InvalidInput, "pdpp request exceeds 1 MiB")); }
        self.output.write_all(&line)?;
        self.output.write_all(b"\n")?;
        self.output.flush()?;
        let mut response_line = String::new();
        self.input.read_line(&mut response_line)?;
        if response_line.len() > 1024 * 1024 { return Err(io::Error::new(io::ErrorKind::InvalidData, "pdpp response exceeds 1 MiB")); }
        let response: Value = serde_json::from_str(&response_line).map_err(io::Error::other)?;
        if response.get("id").and_then(Value::as_str) != Some(&id) { return Err(io::Error::new(io::ErrorKind::InvalidData, "pdpp response id mismatch")); }
        if let Some(error) = response.get("error") { return Err(io::Error::other(error.to_string())); }
        serde_json::from_value(response.get("result").cloned().unwrap_or(Value::Null)).map_err(io::Error::other)
    }

    pub fn compute_hash(&mut self, algorithm: &str, data: &[u8]) -> io::Result<String> {
        let result: Value = self.call("host/compute/hash", json!({
            "algorithm": algorithm,
            "data_base64": base64::engine::general_purpose::STANDARD.encode(data),
        }))?;
        result.get("digest").and_then(Value::as_str).map(str::to_owned)
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing digest"))
    }

    pub fn read_clipboard(&mut self) -> io::Result<Value> {
        self.call("host/clipboard/read", json!({}))
    }

    pub fn write_clipboard(&mut self, text: &str) -> io::Result<Value> {
        self.call("host/clipboard/write", json!({"text": text}))
    }

    pub fn write_file(&mut self, file_ref: &str, offset: u64, data: &[u8]) -> io::Result<usize> {
        let result: Value = self.call("host/file/write", json!({
            "file_ref": file_ref,
            "offset": offset,
            "data_base64": base64::engine::general_purpose::STANDARD.encode(data),
        }))?;
        result.get("written").and_then(Value::as_u64).map(|value| value as usize)
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing written count"))
    }
}
