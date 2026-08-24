package main

import (
	"bufio"
	"encoding/json"
	"os"
)

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      string          `json:"id"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params"`
}

type initializeParams struct {
	PluginID string `json:"plugin_id"`
}

type commandParams struct {
	Command string          `json:"command"`
	Input   json.RawMessage `json:"input"`
}

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	encoder := json.NewEncoder(os.Stdout)
	for scanner.Scan() {
		var message request
		if err := json.Unmarshal(scanner.Bytes(), &message); err != nil {
			continue
		}

		switch message.Method {
		case "initialize":
			var params initializeParams
			if err := json.Unmarshal(message.Params, &params); err != nil {
				writeError(encoder, message.ID, -32602, "Invalid initialize parameters")
				continue
			}
			writeResult(encoder, message.ID, map[string]any{
				"protocol_version": "1.0",
				"plugin_id":        params.PluginID,
				"plugin_version":   "1.0.0",
				"capabilities":     []string{"command.echo"},
			})
		case "health/check":
			writeResult(encoder, message.ID, map[string]any{"status": "healthy"})
		case "command/execute":
			var params commandParams
			if err := json.Unmarshal(message.Params, &params); err != nil || params.Command != "echo" {
				writeError(encoder, message.ID, -32602, "Unknown synthetic command")
				continue
			}
			var input any
			if err := json.Unmarshal(params.Input, &input); err != nil {
				writeError(encoder, message.ID, -32602, "Invalid command input")
				continue
			}
			writeResult(encoder, message.ID, map[string]any{
				"output":   input,
				"language": "go",
			})
		case "shutdown":
			writeResult(encoder, message.ID, map[string]any{"stopped": true})
			return
		default:
			writeError(encoder, message.ID, -32601, "Method not found")
		}
	}
}

func writeResult(encoder *json.Encoder, id string, result any) {
	_ = encoder.Encode(map[string]any{
		"jsonrpc": "2.0",
		"id":      id,
		"result":  result,
	})
}

func writeError(encoder *json.Encoder, id string, code int, message string) {
	_ = encoder.Encode(map[string]any{
		"jsonrpc": "2.0",
		"id":      id,
		"error": map[string]any{
			"code":    code,
			"message": message,
		},
	})
}
