import {
  ApiError,
  type AdminAuditLogEntry,
  type AdminAuditLogListResponse,
  type ApiErrorBody,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export interface AdminAuditLogFilters {
  action?: string;
  result?: string;
  targetType?: string;
  actorId?: string;
  requestId?: string;
  query?: string;
  createdFrom?: string;
  createdTo?: string;
  page?: number;
  pageSize?: number;
}

export interface AuditLogCsvDownload {
  blob: Blob;
  filename: string;
  rowCount: number;
}

function buildAuditLogParams(
  filters: AdminAuditLogFilters,
  includePagination: boolean,
): URLSearchParams {
  const params = new URLSearchParams();
  const mappings: Array<[string, string | undefined]> = [
    ["action", filters.action?.trim()],
    ["result", filters.result?.trim()],
    ["target_type", filters.targetType?.trim()],
    ["actor_id", filters.actorId?.trim()],
    ["request_id", filters.requestId?.trim()],
    ["query", filters.query?.trim()],
    ["created_from", filters.createdFrom],
    ["created_to", filters.createdTo],
  ];
  for (const [key, value] of mappings) {
    if (value) params.set(key, value);
  }
  if (includePagination) {
    params.set("page", String(filters.page ?? 1));
    params.set("page_size", String(filters.pageSize ?? 20));
  }
  return params;
}

export function listAdminAuditLogs(
  filters: AdminAuditLogFilters,
  token: string,
): Promise<AdminAuditLogListResponse> {
  const params = buildAuditLogParams(filters, true);
  return apiRequest<AdminAuditLogListResponse>(
    `/admin/audit-logs?${params.toString()}`,
    {},
    token,
  );
}

export function getAdminAuditLog(
  auditId: string,
  token: string,
): Promise<AdminAuditLogEntry> {
  return apiRequest<AdminAuditLogEntry>(
    `/admin/audit-logs/${encodeURIComponent(auditId)}`,
    {},
    token,
  );
}

function exportFilename(response: Response): string {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? "audit-logs.csv";
}

export async function downloadAdminAuditLogs(
  filters: AdminAuditLogFilters,
  token: string,
): Promise<AuditLogCsvDownload> {
  const params = buildAuditLogParams(filters, false);
  const headers = new Headers({
    Accept: "text/csv",
    Authorization: `Bearer ${token}`,
    "X-Request-ID": `admin_${crypto.randomUUID()}`,
  });
  const response = await fetch(
    `${baseUrl}/admin/audit-logs/export?${params.toString()}`,
    { credentials: "include", headers },
  );
  if (!response.ok) {
    let body: ApiErrorBody = {
      code: "network.unexpected_response",
      message: "审计导出暂时不可用",
      details: {},
      request_id: response.headers.get("X-Request-ID"),
    };
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // 保留最小安全错误。
    }
    throw new ApiError(response.status, body);
  }
  return {
    blob: await response.blob(),
    filename: exportFilename(response),
    rowCount: Number(response.headers.get("X-Exported-Rows") ?? "0"),
  };
}
