import type {
  DesktopAnnouncement,
  DesktopAnnouncementImageUploadResponse,
  DesktopAnnouncementListResponse,
  DesktopAnnouncementWriteRequest,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface DesktopAnnouncementDraft {
  title: string;
  content: string;
  contentType: "text" | "html";
  imageUrlsText: string;
  actionLabel: string;
  actionUrl: string;
  sortOrder: number;
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

export function buildDesktopAnnouncementPayload(
  draft: DesktopAnnouncementDraft,
): DesktopAnnouncementWriteRequest {
  const title = draft.title.trim();
  const content = draft.content.trim();
  const actionLabel = draft.actionLabel.trim();
  const actionUrl = draft.actionUrl.trim();
  if (!title) throw new Error("请填写公告标题");
  if (!content) throw new Error("请填写公告正文");
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
        !item.startsWith("/api/v1/desktop/announcements/assets/"),
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
    starts_at: startsAt,
    ends_at: endsAt,
  };
}

export function listDesktopAnnouncements(token: string): Promise<DesktopAnnouncementListResponse> {
  return apiRequest("/admin/desktop-announcements", {}, token);
}

export function createDesktopAnnouncement(
  token: string,
  payload: DesktopAnnouncementWriteRequest,
): Promise<DesktopAnnouncement> {
  return apiRequest("/admin/desktop-announcements", { method: "POST", body: JSON.stringify(payload) }, token);
}

export function updateDesktopAnnouncement(
  token: string,
  id: string,
  payload: DesktopAnnouncementWriteRequest,
): Promise<DesktopAnnouncement> {
  return apiRequest(`/admin/desktop-announcements/${id}`, { method: "PUT", body: JSON.stringify(payload) }, token);
}

export function publishDesktopAnnouncement(token: string, id: string): Promise<DesktopAnnouncement> {
  return apiRequest(`/admin/desktop-announcements/${id}/publish`, { method: "POST" }, token);
}

export function archiveDesktopAnnouncement(token: string, id: string): Promise<DesktopAnnouncement> {
  return apiRequest(`/admin/desktop-announcements/${id}/archive`, { method: "POST" }, token);
}

export function uploadDesktopAnnouncementImage(
  token: string,
  file: File,
): Promise<DesktopAnnouncementImageUploadResponse> {
  return apiRequest(
    "/admin/desktop-announcements/images",
    {
      method: "POST",
      headers: { "Content-Type": file.type },
      body: file,
    },
    token,
  );
}
