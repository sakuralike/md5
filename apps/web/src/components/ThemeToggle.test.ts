import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemeToggle } from "@password-detective/web-ui/theme-toggle";
import { setTheme } from "@password-detective/web-ui/theme";

describe("ThemeToggle", () => {
  beforeEach(() => {
    setTheme("light");
  });

  afterEach(() => {
    setTheme("light");
  });

  it("renders a native switch with a static accessible name and dynamic state", async () => {
    const html = await renderToString(createSSRApp(ThemeToggle));

    expect(html).toContain('type="button"');
    expect(html).toContain('role="switch"');
    expect(html).toContain('aria-label="切换主题"');
    expect(html).toContain('aria-checked="false"');
    expect(html).not.toContain("aria-describedby");
    expect(html).not.toContain(' id=');
  });

  it("renders disabled controls with the current shared state", async () => {
    setTheme("dark");
    const html = await renderToString(createSSRApp(ThemeToggle, { disabled: true }));

    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("disabled");
  });
});
