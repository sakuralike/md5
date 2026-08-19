import { describe, expect, it, vi } from "vitest";
import { calculateLocalHash } from "./localHash";

describe("local hash service", () => {
  it("calculates all supported algorithms from UTF-8 text locally", async () => {
    await expect(calculateLocalHash("abc", "md5")).resolves.toMatchObject({
      digest: "900150983cd24fb0d6963f7d28e17f72",
      inputBytes: 3,
    });
    await expect(calculateLocalHash("abc", "sha1")).resolves.toMatchObject({
      digest: "a9993e364706816aba3e25717850c26c9cd0d89d",
    });
    await expect(calculateLocalHash("abc", "sha256")).resolves.toMatchObject({
      digest: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    });
    await expect(calculateLocalHash("abc", "sha512")).resolves.toMatchObject({
      digest: "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a" +
        "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
    });
  });

  it("hashes files incrementally and reports progress", async () => {
    const progress = vi.fn();
    const result = await calculateLocalHash(new Blob(["abc"]), "sha256", {
      chunkSize: 64 * 1024,
      onProgress: progress,
    });

    expect(result.digest).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(progress).toHaveBeenLastCalledWith({ processedBytes: 3, totalBytes: 3, percent: 100 });
  });

  it("does not continue after cancellation and enforces the size limit", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(calculateLocalHash("synthetic", "sha256", { signal: controller.signal }))
      .rejects.toMatchObject({ name: "AbortError" });
    await expect(calculateLocalHash("synthetic", "sha256", { maxFileSizeBytes: 4 }))
      .rejects.toThrow("超过本地计算建议上限");
  });
});
