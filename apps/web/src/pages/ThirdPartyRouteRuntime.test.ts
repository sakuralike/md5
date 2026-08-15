import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const pageSources = [
  "ThirdPartyAuthorizePage.vue",
  "AuthorizedApplicationsPage.vue",
];

describe("第三方授权路由运行时回归", () => {
  it.each(pageSources)("%s 不使用未被 RouterView 等待的异步 setup", (fileName) => {
    const source = readFileSync(
      fileURLToPath(new URL(`./${fileName}`, import.meta.url)),
      "utf8",
    );

    expect(source).toContain("onMounted");
    expect(source).toContain("onServerPrefetch");
    expect(source).not.toMatch(/\nawait load\(\);\n/u);
  });
});
