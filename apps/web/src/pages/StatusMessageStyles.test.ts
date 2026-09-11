import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const errorClasses = [
  "border-destructive/40",
  "bg-destructive/10",
  "text-destructive",
] as const;

function pageSource(name: string): string {
  return readFileSync(new URL(`./${name}`, import.meta.url), "utf8");
}

describe("status message styles", () => {
  it.each(["ReputationPage.vue", "SubmissionsPage.vue", "TrustCasesPage.vue"])(
    "%s uses semantic error tokens instead of the removed legacy class",
    (name) => {
      const source = pageSource(name);

      expect(source).not.toMatch(/class="error"/u);
      for (const className of errorClasses) expect(source).toContain(className);
    },
  );

  it("uses the success token for trust-case confirmations", () => {
    const source = pageSource("TrustCasesPage.vue");

    expect(source).not.toMatch(/class="success"/u);
    expect(source).toContain("border-[hsl(var(--success)/0.35)]");
    expect(source).toContain("bg-[hsl(var(--success)/0.12)]");
    expect(source).toContain("text-[hsl(var(--success))]");
  });
});
