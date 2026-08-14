export function plainAnnouncementContent(content: string): string {
  if (typeof DOMParser !== "undefined") {
    const document = new DOMParser().parseFromString(content, "text/html");
    return document.body.textContent?.replace(/\s+/g, " ").trim() ?? "";
  }
  return content.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}
