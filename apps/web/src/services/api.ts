import { ApiError, type ApiErrorBody } from "@password-detective/api-contract";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", `web_${crypto.randomUUID()}`);
  if (options.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`${baseUrl}${path}`, { ...options, headers });
  if (!response.ok) {
    const fallback: ApiErrorBody = {
      code: "network.unexpected_response",
      message: "服务暂时不可用，请稍后重试",
      details: {},
      request_id: response.headers.get("X-Request-ID"),
    };
    let body = fallback;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // 保持不含内部响应正文的安全错误。
    }
    throw new ApiError(response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
