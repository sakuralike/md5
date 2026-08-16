<script setup lang="ts">
import type { CommunityDirectConversationResponse } from "@password-detective/api-contract";
import { onMounted, onServerPrefetch, ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createCommunityIdempotencyKey,
  listCommunityDirectConversations,
  updateCommunityDirectMemberState,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const items = ref<CommunityDirectConversationResponse[]>([]);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const loadingMore = ref(false);
const mutatingIds = ref(new Set<string>());
const error = ref("");

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function isMuted(item: CommunityDirectConversationResponse): boolean {
  return Boolean(item.muted_until && new Date(item.muted_until).getTime() > Date.now());
}

async function load(reset = true): Promise<void> {
  if (reset) loading.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const response = await listCommunityDirectConversations(auth.accessToken, {
      ...(reset || !nextCursor.value ? {} : { cursor: nextCursor.value }),
      includeArchived: true,
      limit: 20,
    });
    items.value = reset ? response.items : [...items.value, ...response.items];
    nextCursor.value = response.next_cursor;
    hasMore.value = response.has_more;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载私信收件箱";
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

async function setArchived(
  item: CommunityDirectConversationResponse,
  archived: boolean,
): Promise<void> {
  if (mutatingIds.value.has(item.id)) return;
  mutatingIds.value = new Set(mutatingIds.value).add(item.id);
  error.value = "";
  try {
    const response = await updateCommunityDirectMemberState(
      item.id,
      { archived },
      auth.accessToken,
      createCommunityIdempotencyKey("direct-member-state"),
    );
    items.value = items.value.map((candidate) =>
      candidate.id === item.id ? { ...candidate, archived_at: response.archived_at } : candidate,
    );
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法更新会话归档状态";
  } finally {
    const next = new Set(mutatingIds.value);
    next.delete(item.id);
    mutatingIds.value = next;
  }
}

async function toggleMuted(item: CommunityDirectConversationResponse): Promise<void> {
  if (mutatingIds.value.has(item.id)) return;
  mutatingIds.value = new Set(mutatingIds.value).add(item.id);
  error.value = "";
  try {
    const mutedUntil = isMuted(item)
      ? null
      : new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
    const response = await updateCommunityDirectMemberState(
      item.id,
      { muted_until: mutedUntil },
      auth.accessToken,
      createCommunityIdempotencyKey("direct-member-state"),
    );
    items.value = items.value.map((candidate) =>
      candidate.id === item.id ? { ...candidate, muted_until: response.muted_until } : candidate,
    );
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法更新会话静音状态";
  } finally {
    const next = new Set(mutatingIds.value);
    next.delete(item.id);
    mutatingIds.value = next;
  }
}

onMounted(() => void load());
onServerPrefetch(() => load());
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-6">
    <div class="rounded-3xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Private conversations</p>
          <h1 class="text-3xl font-semibold tracking-tight text-foreground">私信收件箱</h1>
          <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
            私信正文加密存储且仅会话成员可见；通知只显示最小化摘要，不展示消息内容。
          </p>
        </div>
        <Button variant="outline" :disabled="loading" @click="load()">
          {{ loading ? "刷新中…" : "刷新" }}
        </Button>
      </div>
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>私信操作失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Card>
      <CardHeader>
        <CardTitle>会话列表</CardTitle>
        <CardDescription>归档会话仍可恢复；静音只暂停该会话的新消息提醒。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div v-if="loading" class="space-y-3" aria-label="正在加载私信会话">
          <div v-for="index in 3" :key="index" class="h-24 animate-pulse rounded-xl bg-muted" />
        </div>

        <article
          v-for="item in items"
          v-else
          :key="item.id"
          class="flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <RouterLink
                :to="`/community/messages/${item.id}`"
                class="font-semibold text-foreground hover:underline"
              >
                {{ item.counterpart_display_name }}
              </RouterLink>
              <Badge variant="outline">@{{ item.counterpart_username }}</Badge>
              <Badge v-if="item.unread_count > 0">未读 {{ item.unread_count }}</Badge>
              <Badge v-if="item.archived_at" variant="secondary">已归档</Badge>
              <Badge v-if="isMuted(item)" variant="secondary">静音中</Badge>
            </div>
            <p class="text-sm text-muted-foreground">
              {{ item.last_message_at ? `最近消息 ${formatDate(item.last_message_at)}` : "尚未发送消息" }}
            </p>
          </div>
          <div class="flex shrink-0 flex-wrap gap-2">
            <Button as-child size="sm">
              <RouterLink :to="`/community/messages/${item.id}`">打开会话</RouterLink>
            </Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="mutatingIds.has(item.id)"
              @click="setArchived(item, !item.archived_at)"
            >
              {{ item.archived_at ? "恢复" : "归档" }}
            </Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="mutatingIds.has(item.id)"
              @click="toggleMuted(item)"
            >
              {{ isMuted(item) ? "取消静音" : "静音 7 天" }}
            </Button>
          </div>
        </article>

        <div
          v-if="!loading && items.length === 0"
          class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground"
        >
          暂无私信会话。可从其他用户的社区公开主页发起私信。
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
