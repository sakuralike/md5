package pdpp

import (
	"bufio"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"sync/atomic"
)

type Client struct {
	in  *bufio.Reader
	out io.Writer
	next uint64
}

func NewClient(in io.Reader, out io.Writer) *Client {
	return &Client{in: bufio.NewReaderSize(in, 1024*1024), out: out}
}

func (c *Client) Call(method string, params any, result any) error {
	id := fmt.Sprintf("plugin-host-%d", atomic.AddUint64(&c.next, 1))
	request := map[string]any{"jsonrpc": "2.0", "id": id, "method": method, "params": params}
	line, err := json.Marshal(request)
	if err != nil { return err }
	if len(line) > 1024*1024 { return fmt.Errorf("pdpp request exceeds 1 MiB") }
	if _, err = fmt.Fprintf(c.out, "%s\n", line); err != nil { return err }
	responseLine, err := c.in.ReadBytes('\n')
	if err != nil { return err }
	if len(responseLine) > 1024*1024 { return fmt.Errorf("pdpp response exceeds 1 MiB") }
	var response struct {
		ID string `json:"id"`
		Result json.RawMessage `json:"result"`
		Error *struct { Code int `json:"code"`; Message string `json:"message"` } `json:"error"`
	}
	if err := json.Unmarshal(responseLine, &response); err != nil { return err }
	if response.ID != id { return fmt.Errorf("pdpp response id mismatch") }
	if response.Error != nil { return fmt.Errorf("pdpp host error %d: %s", response.Error.Code, response.Error.Message) }
	return json.Unmarshal(response.Result, result)
}

func (c *Client) ShowNotification(title, message, severity string, durationSeconds int) (json.RawMessage, error) {
	var result json.RawMessage
	err := c.Call("host/ui/notification/show", map[string]any{
		"title": title, "message": message, "severity": severity, "duration_seconds": durationSeconds,
	}, &result)
	return result, err
}

func (c *Client) ComputeHash(algorithm string, data []byte) (string, error) {
	var result struct { Digest string `json:"digest"` }
	err := c.Call("host/compute/hash", map[string]any{
		"algorithm": algorithm, "data_base64": base64.StdEncoding.EncodeToString(data),
	}, &result)
	return result.Digest, err
}

func (c *Client) ReadClipboard() (json.RawMessage, error) {
	var result json.RawMessage
	err := c.Call("host/clipboard/read", map[string]any{}, &result)
	return result, err
}

func (c *Client) WriteClipboard(text string) (json.RawMessage, error) {
	var result json.RawMessage
	err := c.Call("host/clipboard/write", map[string]any{"text": text}, &result)
	return result, err
}

func (c *Client) WriteFile(fileRef string, offset int64, data []byte) (int, error) {
	var result struct {
		Written int `json:"written"`
	}
	err := c.Call("host/file/write", map[string]any{
		"file_ref": fileRef, "offset": offset, "data_base64": base64.StdEncoding.EncodeToString(data),
	}, &result)
	return result.Written, err
}
