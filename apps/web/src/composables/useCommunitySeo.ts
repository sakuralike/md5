import type { CommunitySeoProjection } from "@password-detective/api-contract";
import { inject, provide, shallowRef, type InjectionKey, type Ref } from "vue";
import type { SeoContentKind } from "../lib/seo";

export interface CommunitySeoState {
  kind: SeoContentKind;
  path: string;
  projection: CommunitySeoProjection;
}

interface CommunitySeoContext {
  current: Readonly<Ref<CommunitySeoState | null>>;
  set: (state: CommunitySeoState) => void;
  clear: (path?: string) => void;
}

const communitySeoKey: InjectionKey<CommunitySeoContext> = Symbol("community-seo");

export function provideCommunitySeo(): CommunitySeoContext {
  const current = shallowRef<CommunitySeoState | null>(null);
  const context: CommunitySeoContext = {
    current,
    set: (state) => {
      current.value = state;
    },
    clear: (path) => {
      if (!path || current.value?.path === path) current.value = null;
    },
  };
  provide(communitySeoKey, context);
  return context;
}

export function useCommunitySeo(): CommunitySeoContext {
  const context = inject(communitySeoKey);
  if (context) return context;

  const current = shallowRef<CommunitySeoState | null>(null);
  return {
    current,
    set: () => undefined,
    clear: () => undefined,
  };
}
