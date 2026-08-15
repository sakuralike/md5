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

export interface PublishWebAnnouncementOptions {
  withImage?: boolean;
  actionLabel?: string | null;
  actionUrl?: string | null;
}

const SYNTHETIC_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

async function uploadWebAnnouncementImageForBrowser(
  request: APIRequestContext,
  accessToken: string,
): Promise<string> {
  const upload = await request.post(`${apiBaseUrl}/admin/web-announcements/images`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Origin: adminOrigin,
      "Content-Type": "image/png",
    },
    data: SYNTHETIC_PNG,
  });
  expect(upload.status(), await upload.text()).toBe(201);
  const body = (await upload.json()) as {
    url: string;
    content_type: string;
    size_bytes: number;
    sha256: string;
  };
  expect(body.content_type).toBe("image/png");
  expect(body.size_bytes).toBe(SYNTHETIC_PNG.length);
  expect(body.sha256).toMatch(/^[0-9a-f]{64}$/u);
  return body.url;
}

export async function publishWebAnnouncementForBrowser(
  request: APIRequestContext,
  title: string,
  autoCloseSeconds: number | null,
  options: PublishWebAnnouncementOptions = {},
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
  const adminHeaders = {
    Authorization: `Bearer ${tokens.access_token}`,
    Origin: adminOrigin,
  };
  const existing = await request.get(`${apiBaseUrl}/admin/web-announcements`, { headers: adminHeaders });
  expect(existing.status(), await existing.text()).toBe(200);
  const existingBody = (await existing.json()) as {
    items: Array<{ id: string; status: AnnouncementResponse["status"] }>;
  };
  for (const item of existingBody.items) {
    if (item.status !== "published") continue;
    const archived = await request.post(`${apiBaseUrl}/admin/web-announcements/${item.id}/archive`, {
      headers: adminHeaders,
    });
    expect(archived.status(), await archived.text()).toBe(200);
  }
  const imageUrls = options.withImage
    ? [await uploadWebAnnouncementImageForBrowser(request, tokens.access_token)]
    : [];
  const payload: WebAnnouncementWriteRequest = {
    title,
    content: "这是用于浏览器验收的 Web 公告，不包含真实敏感信息。",
    content_type: "text",
    image_urls: imageUrls,
    action_label: options.actionLabel ?? null,
    action_url: options.actionUrl ?? null,
    sort_order: 10_000,
    auto_close_seconds: autoCloseSeconds,
    starts_at: null,
    ends_at: null,
  };
  const created = await request.post(`${apiBaseUrl}/admin/web-announcements`, {
    headers: {
      ...adminHeaders,
    },
    data: payload,
  });
  expect(created.status(), await created.text()).toBe(201);
  const draft = (await created.json()) as AnnouncementResponse;
  expect(draft.status).toBe("draft");

  const published = await request.post(`${apiBaseUrl}/admin/web-announcements/${draft.id}/publish`, {
    headers: {
      ...adminHeaders,
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

export async function isolateWebAnnouncement(page: Page, title: string): Promise<void> {
  const response = await page.request.get(`${apiBaseUrl}/web/announcements?limit=20`);
  expect(response.status(), await response.text()).toBe(200);
  const body = (await response.json()) as { items: Array<Record<string, unknown> & { title: string }> };
  const target = body.items.find((item) => item.title === title);
  expect(target, `未在公开公告列表找到验收公告：${title}`).toBeDefined();
  await page.route("**/api/v1/web/announcements?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [target] }),
    });
  });
}

export async function clearWebAnnouncementDismissals(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const resetMarker = "web-announcement-e2e-dismissals-reset";
    if (sessionStorage.getItem(resetMarker)) return;
    sessionStorage.setItem(resetMarker, "1");
    for (let index = localStorage.length - 1; index >= 0; index -= 1) {
      const key = localStorage.key(index);
      if (key?.startsWith("web-popup-announcement:")) {
        localStorage.removeItem(key);
      }
    }
  });
}
export async function dismissAllWebAnnouncements(page: Page): Promise<void> {
  const popup = page.getByRole("complementary", { name: "网站公告" });
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (attempt === 0) {
      try {
        await expect(popup).toBeVisible({ timeout: 1_500 });
      } catch {
        return;
      }
    } else if (!(await popup.isVisible())) {
      return;
    }
    await popup.getByRole("button", { name: "关闭公告" }).click();
    await page.waitForTimeout(100);
  }
  throw new Error("未能关闭全部 Web 公告弹窗");
}

export async function focusWebAnnouncement(page: Page, title: string): Promise<void> {
  const popup = page.getByRole("complementary", { name: "网站公告" });
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if ((await popup.getByText(title, { exact: true }).count()) > 0) return;
    await expect(popup).toBeVisible();
    await popup.getByRole("button", { name: "关闭公告" }).click();
  }
  throw new Error(`未能在公告队列中定位标题：${title}`);
}

