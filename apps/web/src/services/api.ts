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

function createHeaders(
  options: RequestInit,
  accessToken?: string,
  accept = "application/json",
): Headers {
  const headers = new Headers(options.headers);
  headers.set("Accept", accept);
  headers.set("X-Request-ID", `web_${createClientId()}`);
  if (options.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  return headers;
}

async function sendRequest(
  path: string,
  options: RequestInit,
  accessToken?: string,
  accept = "application/json",
): Promise<Response> {
  return fetch(`${baseUrl}${path}`, {
    credentials: "include",
    ...options,
    headers: createHeaders(options, accessToken, accept),
  });
}

async function readApiError(response: Response): Promise<ApiErrorBody> {
  const fallback: ApiErrorBody = {
    code: "network.unexpected_response",
    message: "服务暂时不可用，请稍后重试",
    details: {},
    request_id: response.headers.get("X-Request-ID"),
  };
  try {
    return (await response.json()) as ApiErrorBody;
  } catch {
    return fallback;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  let response = await sendRequest(path, options, accessToken);
  if (!response.ok) {
    const body = await readApiError(response);
    if (accessToken && response.status === 401 && body.code === EXPIRED_ACCESS_TOKEN_CODE) {
      const refreshedToken = await refreshAccessToken();
      if (refreshedToken) {
        response = await sendRequest(path, options, refreshedToken);
        if (response.ok) {
          if (response.status === 204) return undefined as T;
          return (await response.json()) as T;
        }
        throw new ApiError(response.status, await readApiError(response));
      }
    }
    throw new ApiError(response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiFileRequest(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${baseUrl}${path}`, {
    credentials: "include",
    ...options,
    headers: createHeaders(options, accessToken),
  });
  if (!response.ok) {
    let message = "文件下载失败，请稍后重试";
    try {
      const body = (await response.json()) as ApiErrorBody;
      message = body.message;
    } catch {
      // 下载失败时不暴露非结构化响应正文。
    }
    throw new Error(message);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "privacy-export.json";
  return { blob: await response.blob(), filename };
}

export async function apiStreamRequest(
  path: string,
  accessToken: string,
  options: { signal: AbortSignal; lastEventId?: string | null },
): Promise<Response> {
  const requestOptions: RequestInit = {
    method: "GET",
    signal: options.signal,
    headers: options.lastEventId ? { "Last-Event-ID": options.lastEventId } : {},
  };
  let response = await sendRequest(path, requestOptions, accessToken, "text/event-stream");
  if (!response.ok) {
    const body = await readApiError(response);
    if (response.status === 401 && body.code === EXPIRED_ACCESS_TOKEN_CODE) {
      const refreshedToken = await refreshAccessToken();
      if (refreshedToken) {
        response = await sendRequest(path, requestOptions, refreshedToken, "text/event-stream");
        if (response.ok) return response;
        throw new ApiError(response.status, await readApiError(response));
      }
    }
    throw new ApiError(response.status, body);
  }
  return response;
}
