# Pdpp Sandbox Core

Windows-only Rust IPC skeleton for the `Pdpp.Sandbox.Core` contract.

The process reads one JSON-RPC 2.0 request per stdin line and writes one response per stdout line. It enforces a 1 MiB message limit, JSON depth limit of 32, string request IDs, object parameters, method allowlisting, and fail-closed responses for methods that are not implemented yet.

Implemented in this slice:

- `sandbox.create`/`sandbox.destroy`: create and remove a Windows AppContainer profile, a controlled work directory, and its ACL grant.
- `fs.grant_read`/`fs.read_chunk`: enforce absolute-path, UNC/Windows-directory denial and size limits, then expose only an opaque file reference and bounded base64 chunks.
- `process.spawn`/`process.terminate`: validate and inherit exactly three caller-provided stdio handles, or open three caller-created local named pipes, create a Windows Job Object with memory, CPU, process-count and kill-on-close limits, start an AppContainer process, and retain native handles behind an opaque job token.
- `canary.run`: injects the complete probe set (`probe`, `environment`, `spawn-child`, `hang`, `oversized-output`) for every task, redacts sensitive values, and returns a destruction proof for the isolated marker.
- `attest.host`: reports AppContainer state and fails closed outside an AppContainer.
- `env.sanitize`: emits a fixed environment allowlist and redirects profile paths without returning requested secret values.

WFP policy installation uses the Windows Filtering Platform API (`FwpmEngineOpen0`/`FwpmFilterAdd0`) when the core has administrator rights, with the signed isolation script as a controlled fallback. Registry ACL state is read through Win32 security APIs and falls back to the script only when the native read cannot access the key. The C# host exposes the `Host.Sandbox` Rust IPC boundary and bounded named-pipe transport; the legacy C# AppContainer path remains the compatibility fallback until the packaged core executable is available.

Build and test on Windows:

```powershell
cargo test --manifest-path packages/pdpp-sandbox-core/Cargo.toml --locked
cargo build --manifest-path packages/pdpp-sandbox-core/Cargo.toml --release
```
