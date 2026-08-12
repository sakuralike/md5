import { afterEach, describe, expect, it, vi } from "vitest";
import { createClientId } from "./clientId";

describe("createClientId", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses randomUUID when the secure-context API is available", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "native-uuid" });

    expect(createClientId()).toBe("native-uuid");
  });

  it("creates an RFC 4122 v4 identifier when randomUUID is unavailable", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(0xab);
        return bytes;
      },
    });

    expect(createClientId()).toBe("abababab-abab-4bab-abab-abababababab");
  });

  it("keeps request identifiers available in legacy browsers without Web Crypto", () => {
    vi.stubGlobal("crypto", undefined);

    expect(createClientId()).toMatch(/^fallback-[a-z0-9]+-[a-z0-9]{4,}$/);
  });
});
