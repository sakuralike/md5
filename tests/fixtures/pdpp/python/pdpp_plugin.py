import json
import sys


def write_result(message_id, result):
    print(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}), flush=True)


def write_error(message_id, code, message):
    print(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": code, "message": message},
            }
        ),
        flush=True,
    )


for line in sys.stdin:
    request = json.loads(line)
    message_id = request["id"]
    method = request["method"]
    parameters = request["params"]

    if method == "initialize":
        write_result(
            message_id,
            {
                "protocol_version": "1.0",
                "plugin_id": parameters["plugin_id"],
                "plugin_version": "1.0.0",
                "capabilities": ["command.echo"],
            },
        )
    elif method == "health/check":
        write_result(message_id, {"status": "healthy"})
    elif method == "lifecycle/migrate":
        write_result(message_id, {"status": "not_required", "steps": []})
    elif method == "command/execute" and parameters["command"] == "echo":
        write_result(
            message_id,
            {"output": parameters["input"], "language": "python"},
        )
    elif method == "shutdown":
        write_result(message_id, {"stopped": True})
        break
    else:
        write_error(message_id, -32601, "Method not found")
