import { describe, expect, it, vi } from "vitest";
import { calculateArchiveFingerprints, normalizeManualFingerprint } from "./fingerprint";

describe("archive fingerprint service", () => {
  it("calculates MD5 and SHA-256 incrementally", async () => {
    const progress = vi.fn();
    const result = await calculateArchiveFingerprints(new Blob(["abc"]), {
      chunkSize: 64 * 1024,
      onProgress: progress,
    });
    expect(result.fingerprints).toEqual([
      {
        algorithm: "sha256",
        digest: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      },
      { algorithm: "md5", digest: "900150983cd24fb0d6963f7d28e17f72" },
    ]);
    expect(progress).toHaveBeenLastCalledWith({ processedBytes: 3, totalBytes: 3, percent: 100 });
  });

  it("detects complete manual fingerprints and rejects malformed input", () => {
    expect(normalizeManualFingerprint("A".repeat(64))).toEqual({
      algorithm: "sha256",
      digest: "a".repeat(64),
    });
    expect(() => normalizeManualFingerprint("not-a-fingerprint")).toThrow("十六进制");
  });

  it("enforces a configurable local file size recommendation", async () => {
    await expect(
      calculateArchiveFingerprints(new Blob(["synthetic"]), { maxFileSizeBytes: 4 }),
    ).rejects.toThrow("超过本地计算建议上限");
  });

  it("supports cancellation before reading file data", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(
      calculateArchiveFingerprints(new Blob(["synthetic"]), { signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});
