import type { CommunityPublicProfileResponse } from "@password-detective/api-contract";
import { resolveApiResourceUrl } from "@/services/api";

type CommunityAvatarProjection = Pick<
  CommunityPublicProfileResponse,
  "avatar_kind" | "avatar_seed" | "avatar_url" | "display_name" | "username"
>;

interface AvatarPalette {
  background: string;
  primary: string;
  secondary: string;
  outline: string;
}

const AVATAR_PALETTES: readonly AvatarPalette[] = [
  { background: "#f5ebff", primary: "#9b5de5", secondary: "#f7b2e7", outline: "#4d1b7b" },
  { background: "#e8f5ff", primary: "#3a86ff", secondary: "#a9def9", outline: "#124d9c" },
  { background: "#e9fbf2", primary: "#22a06b", secondary: "#b8f2d0", outline: "#0f5c3a" },
  { background: "#fff2df", primary: "#ef8354", secondary: "#ffd6a5", outline: "#93401f" },
  { background: "#fdf0f4", primary: "#d1497a", secondary: "#ffc8dd", outline: "#7e1640" },
  { background: "#eef0ff", primary: "#6366f1", secondary: "#c7d2fe", outline: "#3730a3" },
];

function hashSeed(seed: string): number {
  let hash = 2166136261;
  for (const character of seed) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function svgText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .slice(0, 1)
    .toUpperCase() || "?";
}

export function createGeneratedCommunityAvatarUrl(seed: string, displayName: string): string {
  const hash = hashSeed(seed || displayName || "password-detective");
  const palette = AVATAR_PALETTES[hash % AVATAR_PALETTES.length] ?? AVATAR_PALETTES[0];
  const faceX = 40 + (hash % 13);
  const accessoryX = 58 + ((hash >>> 4) % 14);
  const letter = svgText(displayName);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="${letter}"><rect width="120" height="120" rx="60" fill="${palette.background}"/><circle cx="60" cy="62" r="39" fill="${palette.secondary}" opacity=".55"/><path d="M26 101c7-22 22-33 34-33s27 11 34 33" fill="${palette.primary}"/><circle cx="60" cy="52" r="25" fill="#fffaf6" stroke="${palette.outline}" stroke-width="3"/><path d="M36 49c4-21 42-24 48 0-7-7-13-10-24-10s-17 3-24 10Z" fill="${palette.primary}"/><circle cx="${faceX}" cy="54" r="3" fill="${palette.outline}"/><circle cx="${accessoryX}" cy="54" r="3" fill="${palette.outline}"/><path d="M51 65c6 4 12 4 18 0" fill="none" stroke="${palette.outline}" stroke-linecap="round" stroke-width="3"/><circle cx="86" cy="28" r="14" fill="${palette.primary}"/><text x="86" y="33" text-anchor="middle" fill="white" font-family="Arial,sans-serif" font-size="14" font-weight="700">${letter}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export function resolveCommunityAvatarUrl(profile: CommunityAvatarProjection): string {
  if (profile.avatar_url) return resolveApiResourceUrl(profile.avatar_url);
  return createGeneratedCommunityAvatarUrl(profile.avatar_seed, profile.display_name || profile.username);
}
