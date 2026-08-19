export interface PasswordGenerationOptions {
  length: number;
  uppercase: boolean;
  lowercase: boolean;
  digits: boolean;
  symbols: boolean;
}

export type RandomUint32Source = (target: Uint32Array) => Uint32Array;

const CHARACTER_SETS = {
  uppercase: "ABCDEFGHJKLMNPQRSTUVWXYZ",
  lowercase: "abcdefghijkmnopqrstuvwxyz",
  digits: "23456789",
  symbols: "!@#$%^&*()-_=+[]{}:,.?",
} as const;

const MIN_PASSWORD_LENGTH = 12;
const MAX_PASSWORD_LENGTH = 128;

export function generateSecurePassword(
  options: PasswordGenerationOptions,
  randomSource: RandomUint32Source = browserRandomUint32,
): string {
  validateOptions(options);
  const selectedSets = Object.entries(CHARACTER_SETS)
    .filter(([key]) => options[key as keyof typeof CHARACTER_SETS])
    .map(([, characters]) => characters);
  const pool = selectedSets.join("");
  const characters = selectedSets.map((characters) => characters[secureRandomIndex(characters.length, randomSource)]);

  while (characters.length < options.length) {
    characters.push(pool[secureRandomIndex(pool.length, randomSource)]);
  }
  shuffleSecurely(characters, randomSource);
  return characters.join("");
}

export function validatePasswordGenerationOptions(options: PasswordGenerationOptions): void {
  validateOptions(options);
}

function validateOptions(options: PasswordGenerationOptions): void {
  if (!Number.isSafeInteger(options.length) || options.length < MIN_PASSWORD_LENGTH || options.length > MAX_PASSWORD_LENGTH) {
    throw new Error(`密码长度必须在 ${MIN_PASSWORD_LENGTH} 到 ${MAX_PASSWORD_LENGTH} 位之间`);
  }
  if (!options.uppercase && !options.lowercase && !options.digits && !options.symbols) {
    throw new Error("至少选择一种字符类型");
  }
}

function browserRandomUint32(target: Uint32Array): Uint32Array {
  if (typeof globalThis.crypto?.getRandomValues !== "function") {
    throw new Error("当前浏览器不支持密码学随机源");
  }
  return globalThis.crypto.getRandomValues(target);
}

function secureRandomIndex(maxExclusive: number, randomSource: RandomUint32Source): number {
  const uint32Range = 0x1_0000_0000;
  const rejectionLimit = Math.floor(uint32Range / maxExclusive) * maxExclusive;
  let randomValue: number;
  do {
    randomValue = randomSource(new Uint32Array(1))[0] ?? 0;
  } while (randomValue >= rejectionLimit);
  return randomValue % maxExclusive;
}

function shuffleSecurely(characters: string[], randomSource: RandomUint32Source): void {
  for (let index = characters.length - 1; index > 0; index -= 1) {
    const swapIndex = secureRandomIndex(index + 1, randomSource);
    [characters[index], characters[swapIndex]] = [characters[swapIndex]!, characters[index]!];
  }
}
