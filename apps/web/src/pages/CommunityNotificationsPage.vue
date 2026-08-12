<script setup lang="ts">
import type {
  CommunityNotificationKind,
  CommunityNotificationPreferenceItem,
  CommunityNotificationResponse,
} from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Checkbox } from "../components/ui/checkbox";
import { Label } from "../components/ui/label";
import {
  createCommunityIdempotencyKey,
  getCommunityNotificationPreferences,
  listCommunityNotifications,
  markAllCommunityNotificationsRead,
  markCommunityNotificationRead,
  updateCommunityNotificationPreferences,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

interface NotificationFilter {
  value: CommunityNotificationKind | null;
  label: string;
}

const notificationFilters: NotificationFilter[] = [
  { value: null, label: "全部" },
  { value: "mention", label: "提及" },
  { value: "reply", label: "回复" },
  { value: "follow", label: "关注" },
  { value: "like_summary", label: "点赞汇总" },
  { value: "group_application", label: "群组申请" },
  { value: "group_decision", label: "群组决定" },
  { value: "group_role_change", label: "角色变更" },
];

const notificationLabels: Record<CommunityNotificationKind, string> = {
  mention: "提及",
  reply: "回复",
  follow: "关注",
  like_summary: "点赞汇总",
  group_application: "群组申请",
  group_decision: "群组决定",
  group_role_change: "群组角色变更",
};

const auth = useAuthStore();
const items = ref<CommunityNotificationResponse[]>([]);
const preferences = ref<CommunityNotificationPreferenceItem[]>([]);
const selectedKind = ref<CommunityNotificationKind | null>(null);
const unreadCount = ref(0);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const busy = ref(false);
const loadingMore = ref(false);
const markingAll = ref(false);
const savingPreferences = ref(false);
const markingIds = ref(new Set<string>());
const error = ref("");

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function notificationTitle(item: CommunityNotificationResponse): string {
  if (item.kind === "mention") {
    return `${item.actor.username} 在${item.source_type === "post" ? "主题" : "回复"}中提到了你`;
  }
  if (item.kind === "reply") return `${item.actor.username} 回复了你的内容`;
  if (item.kind === "follow") return `${item.actor.username} 关注了你`;
  if (item.kind === "like_summary") return "你的内容收到了新的点赞";
  if (item.kind === "group_application") return `${item.actor.username} 提交了群组加入申请`;
  if (item.kind === "group_decision") return "你的群组申请状态已更新";
  return "你的群组角色已发生变更";
}

function notificationLink(item: CommunityNotificationResponse): string | null {
  if (item.post_id) return `/community/posts/${item.post_id}`;
  if (item.source_type === "user") return `/community/users/${item.actor.username}`;
  return null;
}

function notificationLinkLabel(item: CommunityNotificationResponse): string {
  if (item.post_id) return "查看对应内容";
  return "查看用户主页";
}

async function load(reset = true): Promise<void> {
  if (reset) busy.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const response = await listCommunityNotifications(auth.accessToken, {
      ...(reset || !nextCursor.value ? {} : { cursor: nextCursor.value }),
      limit: 20,
      ...(selectedKind.value ? { kind: selectedKind.value } : {}),
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

async function selectKind(kind: CommunityNotificationKind | null): Promise<void> {
  selectedKind.value = kind;
  await load();
}

async function loadPreferences(): Promise<void> {
  try {
    const response = await getCommunityNotificationPreferences(auth.accessToken);
    preferences.value = response.items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载通知偏好";
  }
}

async function savePreferences(): Promise<void> {
  savingPreferences.value = true;
  error.value = "";
  try {
    const response = await updateCommunityNotificationPreferences(
      { items: preferences.value },
      auth.accessToken,
    );
    preferences.value = response.items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法保存通知偏好";
  } finally {
    savingPreferences.value = false;
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

onMounted(() => {
  void load();
  void loadPreferences();
});
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-6">
    <div class="rounded-3xl border border-white/70 bg-card/75 p-6 shadow-xl backdrop-blur-xl sm:p-8">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Community inbox</p>
          <h1 class="text-3xl font-semibold tracking-tight text-foreground">社区通知中心</h1>
          <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
            集中查看提及、回复、关注和群组治理通知。通知仅保存最小化摘要，不复制完整社区内容。
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
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>通知操作失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Card class="border-white/70 bg-card/75 backdrop-blur-xl">
      <CardHeader>
        <CardTitle>通知类型筛选</CardTitle>
        <CardDescription>未读数量会遵循当前类型筛选，方便逐类处理。</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-wrap gap-2">
        <Button
          v-for="filter in notificationFilters"
          :key="filter.label"
          size="sm"
          :variant="selectedKind === filter.value ? 'default' : 'outline'"
          :disabled="busy"
          @click="selectKind(filter.value)"
        >
          {{ filter.label }}
        </Button>
      </CardContent>
    </Card>

    <Card class="border-white/70 bg-card/75 backdrop-blur-xl">
      <CardHeader>
        <CardTitle>通知接收偏好</CardTitle>
        <CardDescription>
          站内通知设置立即影响未来事件；邮件摘要设置会在邮件摘要投递通道启用后生效。
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-3 border-b border-border pb-2 text-xs font-medium text-muted-foreground">
          <span>通知类型</span>
          <span>站内</span>
          <span>邮件摘要</span>
        </div>
        <div
          v-for="preference in preferences"
          :key="preference.kind"
          class="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3"
        >
          <Label :for="`notification-in-app-${preference.kind}`" class="font-normal">
            {{ notificationLabels[preference.kind] }}
          </Label>
          <Checkbox
            :id="`notification-in-app-${preference.kind}`"
            v-model="preference.in_app_enabled"
            :aria-label="`${notificationLabels[preference.kind]}站内通知`"
          />
          <Checkbox
            :id="`notification-email-${preference.kind}`"
            v-model="preference.email_digest_enabled"
            :aria-label="`${notificationLabels[preference.kind]}邮件摘要`"
          />
        </div>
        <div v-if="preferences.length === 0" class="text-sm text-muted-foreground">
          正在加载通知偏好…
        </div>
        <div class="flex justify-end">
          <Button :disabled="savingPreferences || preferences.length === 0" @click="savePreferences">
            {{ savingPreferences ? "保存中…" : "保存通知偏好" }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card class="border-white/70 bg-card/75 backdrop-blur-xl">
      <CardHeader>
        <CardTitle>通知列表</CardTitle>
        <CardDescription>按时间倒序展示；可进入对应内容或用户主页继续处理。</CardDescription>
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
                <Badge variant="outline">{{ notificationLabels[item.kind] }}</Badge>
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
            v-if="notificationLink(item)"
            :to="notificationLink(item) ?? '/community'"
            class="inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline"
            @click="markRead(item)"
          >
            {{ notificationLinkLabel(item) }}
          </RouterLink>
        </article>

        <div
          v-if="!busy && items.length === 0"
          class="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground"
        >
          当前筛选条件下暂无社区通知。
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
