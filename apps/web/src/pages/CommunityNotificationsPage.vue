<script setup lang="ts">
import type { CommunityNotificationResponse } from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import {
  createCommunityIdempotencyKey,
  listCommunityNotifications,
  markAllCommunityNotificationsRead,
  markCommunityNotificationRead,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const items = ref<CommunityNotificationResponse[]>([]);
const unreadCount = ref(0);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const busy = ref(false);
const loadingMore = ref(false);
const markingAll = ref(false);
const markingIds = ref(new Set<string>());
const error = ref("");

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function notificationTitle(item: CommunityNotificationResponse): string {
  return `${item.actor.username} 在${item.source_type === "post" ? "主题" : "回复"}中提到了你`;
}

async function load(reset = true): Promise<void> {
  if (reset) busy.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const response = await listCommunityNotifications(auth.accessToken, {
      cursor: reset ? undefined : (nextCursor.value ?? undefined),
      limit: 20,
    });
    items.value = reset ? response.items : [...items.value, ...response.items];
    unreadCount.value = response.unread_count;
    nextCursor.value = response.next_cursor;
    hasMore.value = response.has_more;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载社区通知";
  } finally {
    busy.value = false;
    loadingMore.value = false;
  }
}

async function markRead(item: CommunityNotificationResponse): Promise<void> {
  if (item.read_at || markingIds.value.has(item.id)) return;
  markingIds.value = new Set(markingIds.value).add(item.id);
  error.value = "";
  try {
    const response = await markCommunityNotificationRead(
      item.id,
      auth.accessToken,
      createCommunityIdempotencyKey("notification-read"),
    );
    item.read_at = new Date().toISOString();
    unreadCount.value = response.unread_count;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法标记通知已读";
  } finally {
    const next = new Set(markingIds.value);
    next.delete(item.id);
    markingIds.value = next;
  }
}

async function markAllRead(): Promise<void> {
  if (unreadCount.value === 0 || markingAll.value) return;
  markingAll.value = true;
  error.value = "";
  try {
    const response = await markAllCommunityNotificationsRead(
      auth.accessToken,
      createCommunityIdempotencyKey("notifications-read-all"),
    );
    const readAt = new Date().toISOString();
    items.value = items.value.map((item) => ({ ...item, read_at: item.read_at ?? readAt }));
    unreadCount.value = response.unread_count;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法全部标记为已读";
  } finally {
    markingAll.value = false;
  }
}

onMounted(() => load());
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Community inbox</p>
        <h1 class="text-3xl font-semibold tracking-tight text-foreground">社区通知中心</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          接收其他用户在主题或回复中的 @提及。通知仅保存最小化摘要，不复制完整社区内容。
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Badge :variant="unreadCount > 0 ? 'default' : 'secondary'">未读 {{ unreadCount }}</Badge>
        <Button variant="outline" :disabled="busy" @click="load()">
          {{ busy ? "刷新中…" : "刷新" }}
        </Button>
        <Button :disabled="markingAll || unreadCount === 0" @click="markAllRead">
          {{ markingAll ? "处理中…" : "全部已读" }}
        </Button>
      </div>
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>通知操作失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Card>
      <CardHeader>
        <CardTitle>提及我的内容</CardTitle>
        <CardDescription>按时间倒序展示；访问主题后可继续查看对应上下文。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <article
          v-for="item in items"
          :key="item.id"
          class="space-y-3 rounded-xl border p-4"
          :class="item.read_at ? 'border-border/70 bg-background/55' : 'border-primary/40 bg-primary/5'"
        >
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="space-y-1">
              <div class="flex flex-wrap items-center gap-2">
                <p class="font-medium text-foreground">{{ notificationTitle(item) }}</p>
                <Badge :variant="item.read_at ? 'secondary' : 'default'">
                  {{ item.read_at ? "已读" : "未读" }}
                </Badge>
              </div>
              <p class="text-xs text-muted-foreground">{{ formatDate(item.created_at) }}</p>
            </div>
            <Button
              v-if="!item.read_at"
              size="sm"
              variant="outline"
              :disabled="markingIds.has(item.id)"
              @click="markRead(item)"
            >
              {{ markingIds.has(item.id) ? "处理中…" : "标记已读" }}
            </Button>
          </div>
          <p class="rounded-lg bg-muted/60 p-3 text-sm leading-6 text-muted-foreground">
            {{ item.preview }}
          </p>
          <RouterLink
            :to="`/community/posts/${item.post_id}`"
            class="inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline"
            @click="markRead(item)"
          >
            查看对应{{ item.source_type === "post" ? "主题" : "回复" }}
          </RouterLink>
        </article>

        <div
          v-if="!busy && items.length === 0"
          class="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground"
        >
          暂无社区提及通知。
        </div>

        <div v-if="hasMore" class="flex justify-center pt-2">
          <Button variant="outline" :disabled="loadingMore" @click="load(false)">
            {{ loadingMore ? "加载中…" : "加载更多" }}
          </Button>
        </div>
      </CardContent>
    </Card>
  </section>
</template>
