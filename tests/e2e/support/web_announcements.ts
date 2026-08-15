import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { currentTotp } from "./totp";

const apiBaseUrl = "http://127.0.0.1:18100/api/v1";
const adminOrigin = "http://127.0.0.1:15174";

interface BrowserTokenResponse {
  access_token: string;
}

interface AnnouncementResponse {
  id: string;
  title: string;
  auto_close_seconds: number | null;
  status: "draft" | "published" | "archived";
}

interface WebAnnouncementWriteRequest {
  title: string;
  content: string;
  content_type: "text";
  image_urls: string[];
  action_label: string | null;
  action_url: string | null;
  sort_order: number;
  auto_close_seconds: number | null;
  starts_at: string | null;
  ends_at: string | null;
}

export interface PublishedWebAnnouncement {
  id: string;
  title: string;
  autoCloseSeconds: number | null;
}

export async function publishWebAnnouncementForBrowser(
  request: APIRequestContext,
  title: string,
  autoCloseSeconds: number | null,
): Promise<PublishedWebAnnouncement> {
  const username = process.env.E2E_ADMIN_WORKFLOW_USERNAME;
  const password = process.env.E2E_ADMIN_WORKFLOW_PASSWORD;
  const totpSecret = process.env.E2E_ADMIN_WORKFLOW_TOTP_SECRET;
  if (!username || !password || !totpSecret) {
    throw new Error("缺少 Web 公告 E2E 合成管理员配置");
  }

  const login = await request.post(`${apiBaseUrl}/admin/auth/login`, {
    headers: { Origin: adminOrigin },
    data: {
      login: username,
      password,
      totp_code: currentTotp(totpSecret),
    },
  });
  expect(login.status(), await login.text()).toBe(200);
  const tokens = (await login.json()) as BrowserTokenResponse;
  const payload: WebAnnouncementWriteRequest = {
    title,
    content: "这是用于浏览器验收的 Web 公告，不包含真实敏感信息。",
    content_type: "text",
    image_urls: [],
    action_label: null,
    action_url: null,
    sort_order: 9_000 + (Date.now() % 1_000),
    auto_close_seconds: autoCloseSeconds,
    starts_at: null,
    ends_at: null,
  };
  const created = await request.post(`${apiBaseUrl}/admin/web-announcements`, {
    headers: {
      Authorization: `Bearer ${tokens.access_token}`,
      Origin: adminOrigin,
    },
    data: payload,
  });
  expect(created.status(), await created.text()).toBe(201);
  const draft = (await created.json()) as AnnouncementResponse;
  expect(draft.status).toBe("draft");

  const published = await request.post(`${apiBaseUrl}/admin/web-announcements/${draft.id}/publish`, {
    headers: {
      Authorization: `Bearer ${tokens.access_token}`,
      Origin: adminOrigin,
    },
  });
  expect(published.status(), await published.text()).toBe(200);
  const announcement = (await published.json()) as AnnouncementResponse;
  expect(announcement.status).toBe("published");
  expect(announcement.auto_close_seconds).toBe(autoCloseSeconds);
  return {
    id: announcement.id,
    title: announcement.title,
    autoCloseSeconds: announcement.auto_close_seconds,
  };
}

export async function clearWebAnnouncementDismissals(page: Page): Promise<void> {
  await page.addInitScript(() => {
    for (let index = localStorage.length - 1; index >= 0; index -= 1) {
      const key = localStorage.key(index);
      if (key?.startsWith("password_detective_web_announcement_dismissed:")) {
        localStorage.removeItem(key);
      }
    }
  });
}

