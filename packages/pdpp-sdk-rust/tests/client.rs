use pdpp_sdk_rust::Client;
use std::io::Cursor;

#[test]
fn compute_hash_request_uses_pdpp_envelope() {
    let input = Cursor::new(br#"{"jsonrpc":"2.0","id":"plugin-host-1","result":{"digest":"abc"}}
"#);
    let output = Vec::new();
    let mut client = Client::new(input, output);
    let digest = client.compute_hash("sha256", b"synthetic").expect("hash result");
    assert_eq!(digest, "abc");
}

#[test]
fn write_file_request_uses_opaque_reference() {
    let input = Cursor::new(br#"{"jsonrpc":"2.0","id":"plugin-host-1","result":{"written":8}}
"#);
    let output = Vec::new();
    let mut client = Client::new(input, output);
    let written = client.write_file("0123456789abcdef0123456789abcdef", 0, b"synthetic").expect("write result");
    assert_eq!(written, 8);
}
