import base64
import json
from typing import Any, TextIO


class PdppHostClient:
    def __init__(self, input_stream: TextIO, output_stream: TextIO) -> None:
        self._input = input_stream
        self._output = output_stream
        self._next_id = 0

    def call(self, method: str, params: Any) -> Any:
        self._next_id += 1
        request_id = f"plugin-host-{self._next_id}"
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        line = json.dumps(request, separators=(",", ":"))
        if len(line.encode("utf-8")) > 1024 * 1024:
            raise ValueError("pdpp request exceeds 1 MiB")
        self._output.write(line + "\n")
        self._output.flush()
        response_line = self._input.readline()
        if not response_line:
            raise EOFError("pdpp host closed the stream")
        if len(response_line.encode("utf-8")) > 1024 * 1024:
            raise ValueError("pdpp response exceeds 1 MiB")
        response = json.loads(response_line)
        if response.get("id") != request_id:
            raise ValueError("pdpp response id mismatch")
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"pdpp host error {error.get('code')}: {error.get('message')}")
        return response["result"]

    def compute_hash(self, algorithm: str, data: bytes) -> str:
        result = self.call(
            "host/compute/hash",
            {"algorithm": algorithm, "data_base64": base64.b64encode(data).decode("ascii")},
        )
        return str(result["digest"])

    def read_clipboard(self) -> Any:
        return self.call("host/clipboard/read", {})

    def write_clipboard(self, text: str) -> Any:
        return self.call("host/clipboard/write", {"text": text})

    def write_file(self, file_ref: str, offset: int, data: bytes) -> int:
        result = self.call(
            "host/file/write",
            {"file_ref": file_ref, "offset": offset, "data_base64": base64.b64encode(data).decode("ascii")},
        )
        return int(result["written"])
