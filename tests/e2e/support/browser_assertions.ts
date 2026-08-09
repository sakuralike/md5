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
  expect(errors, errors.join("\n")).toEqual([]);
}
