import { createMD5, createSHA256 } from "hash-wasm";
import type { ArchiveFingerprint, FingerprintAlgorithm } from "@password-detective/api-contract";

export interface FingerprintProgress {
  processedBytes: number;
  totalBytes: number;
  percent: number;
}

export interface FingerprintResult {
  fingerprints: ArchiveFingerprint[];
  elapsedMs: number;
}

export interface FingerprintOptions {
  chunkSize?: number;
  signal?: AbortSignal;
  onProgress?: (progress: FingerprintProgress) => void;
  maxFileSizeBytes?: number;
}

export const DEFAULT_MAX_ARCHIVE_SIZE_BYTES = 20 * 1024 * 1024 * 1024;

const LENGTH_TO_ALGORITHM: Record<number, FingerprintAlgorithm> = {
  32: "md5",
  40: "sha1",
  64: "sha256",
  128: "sha512",
};

export async function calculateArchiveFingerprints(
  file: Blob,
  options: FingerprintOptions = {},
): Promise<FingerprintResult> {
  const chunkSize = options.chunkSize ?? 4 * 1024 * 1024;
  const maxFileSizeBytes = options.maxFileSizeBytes ?? DEFAULT_MAX_ARCHIVE_SIZE_BYTES;
  if (chunkSize < 64 * 1024) throw new Error("分块大小不能小于 64 KiB");
  if (!Number.isSafeInteger(maxFileSizeBytes) || maxFileSizeBytes <= 0) {
    throw new Error("文件大小上限配置无效");
  }
  if (file.size > maxFileSizeBytes) {
    throw new Error(`文件超过本地计算建议上限 ${formatBytes(maxFileSizeBytes)}`);
  }
  const startedAt = performance.now();
  const [md5, sha256] = await Promise.all([createMD5(), createSHA256()]);
  md5.init();
  sha256.init();

  let offset = 0;
  while (offset < file.size) {
    throwIfAborted(options.signal);
    const end = Math.min(offset + chunkSize, file.size);
    const chunk = new Uint8Array(await file.slice(offset, end).arrayBuffer());
    throwIfAborted(options.signal);
    md5.update(chunk);
    sha256.update(chunk);
    offset = end;
    options.onProgress?.({
      processedBytes: offset,
      totalBytes: file.size,
      percent: file.size === 0 ? 100 : Math.round((offset / file.size) * 100),
    });
  }
  if (file.size === 0) {
    options.onProgress?.({ processedBytes: 0, totalBytes: 0, percent: 100 });
  }

  return {
    fingerprints: [
      { algorithm: "sha256", digest: sha256.digest("hex") },
      { algorithm: "md5", digest: md5.digest("hex") },
    ],
    elapsedMs: Math.round(performance.now() - startedAt),
  };
}

export function normalizeManualFingerprint(value: string): ArchiveFingerprint {
  const digest = value.trim().toLowerCase();
  if (!/^[0-9a-f]+$/.test(digest)) {
    throw new Error("文件指纹只能包含十六进制字符 0-9、a-f");
  }
  const algorithm = LENGTH_TO_ALGORITHM[digest.length];
  if (!algorithm) {
    throw new Error("请输入完整的 MD5、SHA-1、SHA-256 或 SHA-512 文件指纹");
  }
  return { algorithm, digest };
}

function formatBytes(value: number): string {
  if (value < 1024 * 1024 * 1024) return `${Math.round(value / 1024 / 1024)} MiB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GiB`;
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("指纹计算已取消", "AbortError");
}
