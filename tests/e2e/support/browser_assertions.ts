import { expect, type Page } from "@playwright/test";

export function observeBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}

export function expectNoBrowserErrors(errors: string[]): void {
  const actionable = errors.filter((error) =>
    !error.includes("/community/notifications/stream due to access control checks.") &&
    !error.includes("/community/direct-messages/stream due to access control checks.") &&
    !error.includes("Failed to load resource: Could not connect to server"),
  );
  expect(actionable, actionable.join("\n")).toEqual([]);
}
