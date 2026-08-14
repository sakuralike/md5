<script setup lang="ts">
import type { DesktopAnnouncement } from "@password-detective/api-contract";
import { ExternalLink, Megaphone, X } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { Button } from "@/components/ui/button";
import { plainAnnouncementContent } from "@/lib/announcementContent";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { getPopupAnnouncements } from "@/services/announcements";

const DISMISS_PREFIX = "web-popup-announcement:";

const props = withDefaults(
  defineProps<{
    initialAnnouncements?: DesktopAnnouncement[];
    autoload?: boolean;
  }>(),
  {
    initialAnnouncements: () => [],
    autoload: true,
  },
);

const announcements = ref<DesktopAnnouncement[]>([...props.initialAnnouncements]);
const dismissed = ref(new Set<string>());
const loading = ref(false);

function announcementKey(item: DesktopAnnouncement): string {
  return `${item.id}:${item.revision}`;
}

function readDismissedKeys(): void {
  const next = new Set<string>();
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key?.startsWith(DISMISS_PREFIX)) next.add(key.slice(DISMISS_PREFIX.length));
  }
  dismissed.value = next;
}

function safeLink(value: string | null): string | null {
  if (!value) return null;
  try {
    const base = typeof window === "undefined" ? "http://localhost" : window.location.origin;
    const url = new URL(value, base);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return /^[a-z][a-z0-9+.-]*:\//i.test(value) ? url.href : value;
  } catch {
    return null;
  }
}

const activeAnnouncement = computed(() =>
  announcements.value.find((item) => !dismissed.value.has(announcementKey(item))) ?? null,
);
const plainContent = computed(() =>
  activeAnnouncement.value ? plainAnnouncementContent(activeAnnouncement.value.content) : "",
);
const imageUrl = computed(() => activeAnnouncement.value?.image_urls[0] ?? null);
const actionUrl = computed(() => safeLink(activeAnnouncement.value?.action_url ?? null));

function dismiss(): void {
  const item = activeAnnouncement.value;
  if (!item) return;
  const key = announcementKey(item);
  localStorage.setItem(`${DISMISS_PREFIX}${key}`, "dismissed");
  dismissed.value = new Set([...dismissed.value, key]);
}

async function loadAnnouncements(): Promise<void> {
  if (loading.value) return;
  loading.value = true;
  try {
    announcements.value = (await getPopupAnnouncements()).items;
  } catch {
    // 公告不可用不阻断网站主流程。
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  readDismissedKeys();
  if (props.autoload) void loadAnnouncements();
});
</script>

<template>
  <aside
    v-if="activeAnnouncement"
    class="fixed bottom-4 right-4 z-50 w-[calc(100%-2rem)] max-w-sm sm:bottom-6 sm:right-6"
    aria-live="polite"
    aria-label="网站公告"
  >
    <Card class="overflow-hidden border-primary/20 bg-card/95 shadow-2xl backdrop-blur">
      <a
        v-if="imageUrl && actionUrl"
        :href="actionUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :aria-label="activeAnnouncement.action_label ?? `打开${activeAnnouncement.title}`"
      >
        <img :src="imageUrl" :alt="activeAnnouncement.title" class="max-h-48 w-full object-cover" />
      </a>
      <img v-else-if="imageUrl" :src="imageUrl" :alt="activeAnnouncement.title" class="max-h-48 w-full object-cover" />

      <CardHeader class="flex-row items-start gap-3 space-y-0 pb-3">
        <span class="rounded-full bg-primary/10 p-2 text-primary" aria-hidden="true">
          <Megaphone class="size-4" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="text-xs font-medium text-muted-foreground">站点公告</p>
          <CardTitle class="mt-1 text-base leading-6">{{ activeAnnouncement.title }}</CardTitle>
        </div>
        <Button variant="ghost" size="icon" type="button" aria-label="关闭公告" @click="dismiss">
          <X class="size-4" />
        </Button>
      </CardHeader>

      <CardContent v-if="plainContent" class="whitespace-pre-line pb-4 text-sm leading-6 text-muted-foreground">
        {{ plainContent }}
      </CardContent>

      <CardFooter v-if="actionUrl" class="justify-end border-t bg-muted/30 py-3">
        <Button size="sm" as-child>
          <a :href="actionUrl" target="_blank" rel="noopener noreferrer">
            {{ activeAnnouncement.action_label || "查看详情" }}
            <ExternalLink class="ml-2 size-4" />
          </a>
        </Button>
      </CardFooter>
    </Card>
  </aside>
</template>
