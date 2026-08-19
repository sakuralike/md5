import type { CommunityOwnProfileResponse } from "@password-detective/api-contract";
import { computed, shallowRef, type ComputedRef } from "vue";
import { resolveCommunityAvatarUrl } from "@/lib/communityAvatar";
import { getCommunityOwnProfile } from "@/services/community";

const activeUserId = shallowRef<string | null>(null);
const activeProfile = shallowRef<CommunityOwnProfileResponse | null>(null);
let requestSequence = 0;

export function useCommunityAvatar(): {
  avatarSrc: ComputedRef<string | null>;
  hydrate: (userId: string, accessToken: string) => Promise<void>;
  apply: (profile: CommunityOwnProfileResponse) => void;
  clear: () => void;
} {
  const avatarSrc = computed(() => {
    if (!activeProfile.value) return null;
    return resolveCommunityAvatarUrl(activeProfile.value);
  });

  async function hydrate(userId: string, accessToken: string): Promise<void> {
    if (!userId || !accessToken) return;
    if (activeUserId.value === userId && activeProfile.value) return;
    const sequence = ++requestSequence;
    activeUserId.value = userId;
    activeProfile.value = null;
    try {
      const profile = await getCommunityOwnProfile(accessToken);
      if (sequence === requestSequence && activeUserId.value === userId) {
        activeProfile.value = profile;
      }
    } catch {
      if (sequence === requestSequence && activeUserId.value === userId) {
        activeProfile.value = null;
      }
    }
  }

  function apply(profile: CommunityOwnProfileResponse): void {
    activeProfile.value = profile;
  }

  function clear(): void {
    requestSequence += 1;
    activeUserId.value = null;
    activeProfile.value = null;
  }

  return {
    avatarSrc,
    hydrate,
    apply,
    clear,
  };
}
