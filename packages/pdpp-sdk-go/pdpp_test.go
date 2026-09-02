package pdpp

import (
	"bytes"
	"strings"
	"testing"
)

func TestClientComputesHashRequest(t *testing.T) {
	input := `{"jsonrpc":"2.0","id":"plugin-host-1","result":{"digest":"abc"}}` + "\n"
	var output bytes.Buffer
	client := NewClient(strings.NewReader(input), &output)
	digest, err := client.ComputeHash("sha256", []byte("synthetic"))
	if err != nil { t.Fatal(err) }
	if digest != "abc" { t.Fatalf("digest=%q", digest) }
	if !strings.Contains(output.String(), `"method":"host/compute/hash"`) { t.Fatal("missing method") }
}

func TestClientWritesFileRequest(t *testing.T) {
	input := `{"jsonrpc":"2.0","id":"plugin-host-1","result":{"written":8}}` + "\n"
	var output bytes.Buffer
	client := NewClient(strings.NewReader(input), &output)
	written, err := client.WriteFile("0123456789abcdef0123456789abcdef", 0, []byte("synthetic"))
	if err != nil { t.Fatal(err) }
	if written != 8 { t.Fatalf("written=%d", written) }
	if !strings.Contains(output.String(), `"method":"host/file/write"`) { t.Fatal("missing method") }
}
