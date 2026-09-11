import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const themeFiles = [
  ["Web", new URL("../../../apps/web/src/index.css", import.meta.url)],
  ["Admin", new URL("../../../apps/admin/src/index.css", import.meta.url)],
] as const;

function hslToRgb(hue: number, saturation: number, lightness: number): [number, number, number] {
  const normalizedSaturation = saturation / 100;
  const normalizedLightness = lightness / 100;
  const amplitude = normalizedSaturation * Math.min(normalizedLightness, 1 - normalizedLightness);
  const channel = (offset: number): number => {
    const position = (offset + hue / 30) % 12;
    return 255 * (
      normalizedLightness
      - amplitude * Math.max(-1, Math.min(position - 3, 9 - position, 1))
    );
  };
  return [channel(0), channel(8), channel(4)];
}

function luminance(rgb: readonly number[]): number {
  const linear = rgb.map((channel) => {
    const normalized = channel / 255;
    return normalized <= 0.04045
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function contrastWithWhite(rgb: readonly number[], brightness = 1): number {
  const adjusted = rgb.map((channel) => Math.min(255, channel * brightness));
  return 1.05 / (luminance(adjusted) + 0.05);
}

function tokenValue(css: string, token: string): [number, number, number] {
  const match = new RegExp(`${token}:\\s*(\\d+)\\s+(\\d+)%\\s+(\\d+)%`, "u").exec(css);
  if (!match) throw new Error(`Missing ${token}`);
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

describe.each(themeFiles)("%s gradient theme contract", (_name, file) => {
  const css = readFileSync(file, "utf8");

  it("defines the same dedicated white foreground in light and dark themes", () => {
    expect(css.match(/--gradient-foreground:\s*0 0% 100%/gu)).toHaveLength(2);
    expect(css).toContain("color: hsl(var(--gradient-foreground))");
  });

  it("keeps every gradient stop above AA contrast after hover brightening", () => {
    for (const token of ["--gradient-start", "--gradient-middle", "--gradient-end"] as const) {
      expect(css.match(new RegExp(`${token}:\\s*\\d+\\s+\\d+%\\s+\\d+%`, "gu"))).toHaveLength(2);
      const contrast = contrastWithWhite(hslToRgb(...tokenValue(css, token)), 1.08);
      expect(contrast, `${token} hover contrast`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("uses an opaque, AA-compliant disabled treatment", () => {
    expect(css.match(/--gradient-disabled:\s*\d+\s+\d+%\s+\d+%/gu)).toHaveLength(2);
    const contrast = contrastWithWhite(hslToRgb(...tokenValue(css, "--gradient-disabled")));

    expect(contrast).toBeGreaterThanOrEqual(4.5);
    expect(css).toMatch(/\.btn-gradient:disabled\s*\{[^}]*opacity:\s*1;/su);
    expect(css).toMatch(/\.btn-gradient:disabled\s*\{[^}]*background:\s*hsl\(var\(--gradient-disabled\)\);/su);
  });
});
