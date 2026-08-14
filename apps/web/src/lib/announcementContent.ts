export function plainAnnouncementContent(content: string): string {
  if (typeof DOMParser !== "undefined") {
    const document = new DOMParser().parseFromString(content, "text/html");
    return document.body.textContent?.replace(/\s+/g, " ").trim() ?? "";
  }
  return content.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}


export function announcementAutoCloseMilliseconds(seconds: number | null): number | null {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 1 || seconds > 86_400) {
    return null;
  }
  return Math.trunc(seconds) * 1_000;
}
