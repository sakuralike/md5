import { afterEach, describe, expect, it, vi } from "vitest";
import type { DesktopPluginBuildProof } from "@password-detective/api-contract";
import { attachPluginBuildProof } from "./developerPlugins";

const proof: DesktopPluginBuildProof = {
  schema: "pd.plugin.build-proof/v1",
  git_commit: "a".repeat(40),
  package_sha256: "b".repeat(64),
  rebuild_sha256: "c".repeat(64),
  content_reproducible: true,
  provenance: {
    schema: "pd.plugin.provenance/v1",
    source_commit: "a".repeat(40),
    source_files: [{ path: "source/Program.cs", size_bytes: 12, sha256: "d".repeat(64) }],
    sbom: { path: "sbom.cdx.json", size_bytes: 24, sha256: "e".repeat(64) },
    binaries: [{ path: "bin/windows-x64/plugin.dll", size_bytes: 36, sha256: "f".repeat(64) }],
  },
  toolchain: { dotnet: "10.0" },
};

describe("developer plugin service", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the build proof with version and GitHub artifact binding", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "version-1", version: 7 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-build-proof" });

    await attachPluginBuildProof(
      "access-token",
      { id: "version/with space", version: 7 },
      proof,
      33744780271,
      9889337066,
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/developer/plugin-versions/version%2Fwith%20space/build-proof");
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer access-token");
    expect((init.headers as Headers).get("Idempotency-Key")).toBe("plugin-build-proof-synthetic-build-proof");
    expect(JSON.parse(String(init.body))).toEqual({
      version: 7,
      architecture: "windows-x64",
      github_repository: "sakuralike/md5",
      github_run_id: 33744780271,
      github_artifact_id: 9889337066,
      proof,
    });
  });
});
