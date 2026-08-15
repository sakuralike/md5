import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

describe("第三方应用治理路由运行时回归", () => {
  it("不使用未被 RouterView 等待的异步 setup", () => {
    const source = readFileSync(
      fileURLToPath(new URL("./ThirdPartyAppsPage.vue", import.meta.url)),
      "utf8",
    );

    expect(source).toContain("onMounted");
    expect(source).toContain("onServerPrefetch");
    expect(source).not.toMatch(/\nawait load\(\);\n/u);
  });
});
