import {
  createMD5,
  createSHA1,
  createSHA256,
  createSHA512,
  type IHasher,
} from "hash-wasm";

export type LocalHashAlgorithm = "md5" | "sha1" | "sha256" | "sha512";

export interface LocalHashAlgorithmOption {
  value: LocalHashAlgorithm;
  label: string;
  description: string;
  digestLength: number;
}

export const LOCAL_HASH_ALGORITHMS: readonly LocalHashAlgorithmOption[] = [
  { value: "md5", label: "MD5", description: "128 位摘要，适合兼容性校验", digestLength: 32 },
  { value: "sha1", label: "SHA-1", description: "160 位摘要，适合旧系统兼容", digestLength: 40 },
  { value: "sha256", label: "SHA-256", description: "256 位摘要，通用推荐", digestLength: 64 },
  { value: "sha512", label: "SHA-512", description: "512 位摘要，较高安全余量", digestLength: 128 },
];

export interface LocalHashProgress {
  processedBytes: number;
  totalBytes: number;
  percent: number;
}

export interface LocalHashOptions {
  chunkSize?: number;
  signal?: AbortSignal;
  onProgress?: (progress: LocalHashProgress) => void;
  maxFileSizeBytes?: number;
}

export interface LocalHashResult {
  algorithm: LocalHashAlgorithm;
  digest: string;
  elapsedMs: number;
  inputBytes: number;
}

export const DEFAULT_MAX_LOCAL_HASH_FILE_BYTES = 2 * 1024 * 1024 * 1024;

const HASH_FACTORIES: Record<LocalHashAlgorithm, () => Promise<IHasher>> = {
  md5: createMD5,
  sha1: createSHA1,
  sha256: createSHA256,
  sha512: createSHA512,
};

export async function calculateLocalHash(
  source: string | Blob,
  algorithm: LocalHashAlgorithm,
  options: LocalHashOptions = {},
): Promise<LocalHashResult> {
  const chunkSize = options.chunkSize ?? 4 * 1024 * 1024;
  const maxFileSizeBytes = options.maxFileSizeBytes ?? DEFAULT_MAX_LOCAL_HASH_FILE_BYTES;
  if (chunkSize < 64 * 1024) throw new Error("分块大小不能小于 64 KiB");
  if (!Number.isSafeInteger(maxFileSizeBytes) || maxFileSizeBytes <= 0) {
    throw new Error("文件大小上限配置无效");
  }

  const inputBytes = typeof source === "string" ? new TextEncoder().encode(source).byteLength : source.size;
  if (inputBytes > maxFileSizeBytes) {
    throw new Error("输入内容超过本地计算建议上限");
  }

  if (!(algorithm in HASH_FACTORIES)) throw new Error("不支持的本地摘要算法");
  const hasher = await HASH_FACTORIES[algorithm]();
  hasher.init();
  const startedAt = performance.now();

  if (typeof source === "string") {
    const sourceBytes = new TextEncoder().encode(source);
    throwIfAborted(options.signal);
    hasher.update(sourceBytes);
    options.onProgress?.({ processedBytes: inputBytes, totalBytes: inputBytes, percent: 100 });
  } else {
    let offset = 0;
    while (offset < source.size) {
      throwIfAborted(options.signal);
      const end = Math.min(offset + chunkSize, source.size);
      const chunk = new Uint8Array(await source.slice(offset, end).arrayBuffer());
      throwIfAborted(options.signal);
      hasher.update(chunk);
      offset = end;
      options.onProgress?.({
        processedBytes: offset,
        totalBytes: source.size,
        percent: source.size === 0 ? 100 : Math.round((offset / source.size) * 100),
      });
    }
    if (source.size === 0) {
      options.onProgress?.({ processedBytes: 0, totalBytes: 0, percent: 100 });
    }
  }

  throwIfAborted(options.signal);
  return {
    algorithm,
    digest: hasher.digest("hex"),
    elapsedMs: Math.round(performance.now() - startedAt),
    inputBytes,
  };
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("本地摘要计算已取消", "AbortError");
}
