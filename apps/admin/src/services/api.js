import { ApiError } from "@password-detective/api-contract";
const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
export async function apiRequest(path, options = {}, token) {
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("X-Request-ID", `admin_${crypto.randomUUID()}`);
    if (options.body)
        headers.set("Content-Type", "application/json");
    if (token)
        headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${baseUrl}${path}`, { ...options, headers });
    if (!response.ok) {
        let body = {
            code: "network.unexpected_response",
            message: "管理服务暂时不可用",
            details: {},
            request_id: response.headers.get("X-Request-ID"),
        };
        try {
            body = (await response.json());
        }
        catch { /* 安全回退 */ }
        throw new ApiError(response.status, body);
    }
    return (await response.json());
}
