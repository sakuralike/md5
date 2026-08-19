import { describe, expect, it } from "vitest";
import { generateSecurePassword, validatePasswordGenerationOptions } from "./passwordGenerator";

function deterministicRandom(target: Uint32Array): Uint32Array {
  target[0] = 7;
  return target;
}

describe("secure password generator", () => {
  it("creates a password with every selected character class", () => {
    const password = generateSecurePassword(
      { length: 24, uppercase: true, lowercase: true, digits: true, symbols: true },
      deterministicRandom,
    );

    expect(password).toHaveLength(24);
    expect(password).toMatch(/[A-Z]/);
    expect(password).toMatch(/[a-z]/);
    expect(password).toMatch(/[2-9]/);
    expect(Array.from(password).some((character) => "!@#$%^&*()-_=+[]{}:,.?".includes(character))).toBe(true);
  });

  it("rejects weak configuration instead of silently weakening the result", () => {
    expect(() => validatePasswordGenerationOptions({
      length: 8,
      uppercase: true,
      lowercase: true,
      digits: false,
      symbols: false,
    })).toThrow("12 到 128");
    expect(() => validatePasswordGenerationOptions({
      length: 24,
      uppercase: false,
      lowercase: false,
      digits: false,
      symbols: false,
    })).toThrow("至少选择");
  });
});
