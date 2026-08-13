import { ApiError, type ApiErrorBody } from "@password-detective/api-contract";
import { createClientId } from "@/lib/clientId";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const EXPIRED_ACCESS_TOKEN_CODE = "auth.access_token_expired";

type AccessTokenRefreshHandler = () => Promise<string | null>;

let accessTokenRefreshHandler: AccessTokenRefreshHandler | null = null;
let accessTokenRefreshPromise: Promise<string | null> | null = null;

export function setAccessTokenRefreshHandler(
  handler: AccessTokenRefreshHandler | null,
): void {
  accessTokenRefreshHandler = handler;
  accessTokenRefreshPromise = null;
}

async function refreshAccessToken(): Promise<string | null> {
  if (!accessTokenRefreshHandler) return null;
  if (!accessTokenRefreshPromise) {
    accessTokenRefreshPromise = accessTokenRefreshHandler().finally(() => {
      accessTokenRefreshPromise = null;
    });
  }
  return accessTokenRefreshPromise;
}

function createHeaders(options: RequestInit, token?: string): Headers {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", `admin_${createClientId()}`);
  if (typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function sendRequest(
  path: string,
  options: RequestInit,
  token?: string,
): Promise<Response> {
  return fetch(`${baseUrl}${path}`, {
    credentials: "include",
    ...options,
    headers: createHeaders(options, token),
  });
}

async function readApiError(response: Response): Promise<ApiErrorBody> {
  let body: ApiErrorBody = {
    code: "network.unexpected_response",
    message: "管理服务暂时不可用",
    details: {},
    request_id: response.headers.get("X-Request-ID"),
  };
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // 安全回退：不暴露非结构化服务端响应正文。
  }
  return body;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  let response = await sendRequest(path, options, token);
  if (!response.ok) {
    const body = await readApiError(response);
    if (token && response.status === 401 && body.code === EXPIRED_ACCESS_TOKEN_CODE) {
      const refreshedToken = await refreshAccessToken();
      if (refreshedToken) {
        response = await sendRequest(path, options, refreshedToken);
        if (response.ok) return (await response.json()) as T;
        throw new ApiError(response.status, await readApiError(response));
      }
    }
    throw new ApiError(response.status, body);
  }
  return (await response.json()) as T;
}
