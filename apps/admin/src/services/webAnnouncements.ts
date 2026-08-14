import type {
  WebAnnouncement,
  WebAnnouncementImageUploadResponse,
  WebAnnouncementListResponse,
  WebAnnouncementWriteRequest,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface WebAnnouncementDraft {
  title: string;
  content: string;
  contentType: "text" | "html";
  imageUrlsText: string;
  actionLabel: string;
  actionUrl: string;
  sortOrder: number;
  autoCloseSeconds: number;
  startsAt: string;
  endsAt: string;
}

function toIsoOrNull(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) throw new Error("公告生效时间格式无效");
  return parsed.toISOString();
}

export function buildWebAnnouncementPayload(
  draft: WebAnnouncementDraft,
): WebAnnouncementWriteRequest {
  const title = draft.title.trim();
  const content = draft.content.trim();
  const actionLabel = draft.actionLabel.trim();
  const actionUrl = draft.actionUrl.trim();
  if (!title) throw new Error("请填写公告标题");
  if (!content) throw new Error("请填写公告正文");
  const autoCloseSeconds = Number(draft.autoCloseSeconds);
  if (!Number.isFinite(autoCloseSeconds) || autoCloseSeconds < 0 || autoCloseSeconds > 86_400) {
    throw new Error("自动关闭秒数必须是 0 到 86400 之间的数字");
  }
  if (actionUrl && !/^https?:\/\//i.test(actionUrl)) throw new Error("跳转地址必须使用 HTTP(S)");
  const imageUrls = draft.imageUrlsText
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (imageUrls.length > 8) throw new Error("单条公告最多配置 8 张图片");
  if (
    imageUrls.some(
      (item) =>
        !/^https?:\/\//i.test(item) &&
        !item.startsWith("/api/v1/web/announcements/assets/"),
    )
  ) {
    throw new Error("图片地址必须使用 HTTP(S) 或已上传的公告图片地址");
  }
  const startsAt = toIsoOrNull(draft.startsAt);
  const endsAt = toIsoOrNull(draft.endsAt);
  if (startsAt && endsAt && new Date(endsAt) <= new Date(startsAt)) {
    throw new Error("结束时间必须晚于开始时间");
  }
  return {
    title,
    content,
    content_type: draft.contentType,
    image_urls: [...new Set(imageUrls)],
    action_label: actionLabel || null,
    action_url: actionUrl || null,
    sort_order: Number.isFinite(Number(draft.sortOrder)) ? Number(draft.sortOrder) : 0,
    auto_close_seconds: autoCloseSeconds === 0 ? null : Math.trunc(autoCloseSeconds),
    starts_at: startsAt,
    ends_at: endsAt,
  };
}

export function listWebAnnouncements(token: string): Promise<WebAnnouncementListResponse> {
  return apiRequest("/admin/web-announcements", {}, token);
}

export function createWebAnnouncement(
  token: string,
  payload: WebAnnouncementWriteRequest,
): Promise<WebAnnouncement> {
  return apiRequest("/admin/web-announcements", { method: "POST", body: JSON.stringify(payload) }, token);
}

export function updateWebAnnouncement(
  token: string,
  id: string,
  payload: WebAnnouncementWriteRequest,
): Promise<WebAnnouncement> {
  return apiRequest(`/admin/web-announcements/${id}`, { method: "PUT", body: JSON.stringify(payload) }, token);
}

export function publishWebAnnouncement(token: string, id: string): Promise<WebAnnouncement> {
  return apiRequest(`/admin/web-announcements/${id}/publish`, { method: "POST" }, token);
}

export function archiveWebAnnouncement(token: string, id: string): Promise<WebAnnouncement> {
  return apiRequest(`/admin/web-announcements/${id}/archive`, { method: "POST" }, token);
}

export function uploadWebAnnouncementImage(
  token: string,
  file: File,
): Promise<WebAnnouncementImageUploadResponse> {
  return apiRequest(
    "/admin/web-announcements/images",
    {
      method: "POST",
      headers: { "Content-Type": file.type },
      body: file,
    },
    token,
  );
}
