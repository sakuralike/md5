import io
import json

from pdpp_sdk import PdppHostClient


def test_compute_hash_request() -> None:
    input_stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": "plugin-host-1", "result": {"digest": "abc"}}) + "\n")
    output_stream = io.StringIO()
    client = PdppHostClient(input_stream, output_stream)
    assert client.compute_hash("sha256", b"synthetic") == "abc"
    assert "host/compute/hash" in output_stream.getvalue()


def test_write_file_request() -> None:
    input_stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": "plugin-host-1", "result": {"written": 8}}) + "\n")
    output_stream = io.StringIO()
    client = PdppHostClient(input_stream, output_stream)
    assert client.write_file("0123456789abcdef0123456789abcdef", 0, b"synthetic") == 8
    assert "host/file/write" in output_stream.getvalue()
