export interface BrowserCrypto {
  randomUUID?: () => string;
  getRandomValues?: <T extends ArrayBufferView | null>(array: T) => T;
}

let fallbackSequence = 0;

function bytesToUuid(bytes: Uint8Array): string {
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * 生成浏览器侧请求标识。HTTP 非安全上下文通常没有 crypto.randomUUID，
 * 因此优先回退到仍可用的 getRandomValues，并保留极旧环境的唯一性兜底。
 */
export function createClientId(): string {
  const cryptoApi = globalThis.crypto as BrowserCrypto | undefined;
  if (typeof cryptoApi?.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  if (typeof cryptoApi?.getRandomValues === "function") {
    return bytesToUuid(cryptoApi.getRandomValues(new Uint8Array(16)));
  }

  fallbackSequence = (fallbackSequence + 1) % Number.MAX_SAFE_INTEGER;
  const timestamp = Date.now().toString(36);
  const sequence = fallbackSequence.toString(36).padStart(4, "0");
  return `fallback-${timestamp}-${sequence}`;
}
