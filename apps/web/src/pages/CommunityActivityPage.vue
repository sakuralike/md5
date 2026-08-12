<script setup lang="ts">
import type {
  CommunityActivityFeed,
  CommunityActivityItem,
  CommunityActivityPreferenceResponse,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Checkbox } from "../components/ui/checkbox";
import { Label } from "../components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  getCommunityActivityPreferences,
  listCommunityActivity,
  updateCommunityActivityPreferences,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const feed = ref<CommunityActivityFeed>("latest");
const items = ref<CommunityActivityItem[]>([]);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const busy = ref(false);
const loadingMore = ref(false);
const savingPreferences = ref(false);
const error = ref("");
const preferences = ref<CommunityActivityPreferenceResponse>({
  share_group_joins: true,
  share_follows: true,
});

const canUsePrivateFeeds = computed(() => auth.isAuthenticated);

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function activityTitle(item: CommunityActivityItem): string {
  if (item.kind === "post_published") return `${item.actor.username} 发布了主题`;
  if (item.kind === "comment_published") return `${item.actor.username} 回复了主题`;
  if (item.kind === "group_joined") return `${item.actor.username} 加入了群组`;
  return `${item.actor.username} 关注了 ${item.target_username ?? "一位用户"}`;
}

function activityLink(item: CommunityActivityItem): string | null {
  if (item.post_id) return `/community/posts/${item.post_id}`;
  if (item.group_slug) return `/community/groups/${item.group_slug}`;
  if (item.target_username) return `/community/users/${item.target_username}`;
  return null;
}

async function load(reset = true): Promise<void> {
  if (reset) busy.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const response = await listCommunityActivity(feed.value, auth.accessToken || undefined, {
      cursor: reset ? undefined : (nextCursor.value ?? undefined),
      limit: 20,
    });
    items.value = reset ? response.items : [...items.value, ...response.items];
    nextCursor.value = response.next_cursor;
    hasMore.value = response.has_more;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载社区动态";
  } finally {
    busy.value = false;
    loadingMore.value = false;
  }
}

async function selectFeed(value: string | number): Promise<void> {
  const nextFeed = String(value) as CommunityActivityFeed;
  if (nextFeed !== "latest" && !canUsePrivateFeeds.value) return;
  feed.value = nextFeed;
  await load();
}

async function savePreferences(): Promise<void> {
  if (!auth.isAuthenticated) return;
  savingPreferences.value = true;
  error.value = "";
  try {
    preferences.value = await updateCommunityActivityPreferences(
      preferences.value,
      auth.accessToken,
    );
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法保存动态公开偏好";
  } finally {
    savingPreferences.value = false;
  }
}

onMounted(async () => {
  await load();
  if (auth.isAuthenticated) {
    try {
      preferences.value = await getCommunityActivityPreferences(auth.accessToken);
    } catch {
      // 动态列表仍可独立使用，偏好加载失败时保留安全默认值。
    }
  }
});
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-6">
    <div class="rounded-3xl border border-white/70 bg-card/75 p-6 shadow-xl backdrop-blur-xl sm:p-8">
      <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Community pulse</p>
      <div class="mt-3 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="space-y-2">
          <h1 class="text-3xl font-semibold tracking-tight text-foreground">社区动态信息流</h1>
          <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
            聚合公开发帖、回复、加入公开群组与关注动作，并在读取时应用拉黑、静音、内容状态和群组可见性边界。
          </p>
        </div>
        <Button variant="outline" :disabled="busy" @click="load()">
          {{ busy ? "刷新中…" : "刷新动态" }}
        </Button>
      </div>
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>动态操作失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Tabs :model-value="feed" @update:model-value="selectFeed">
      <TabsList class="grid w-full grid-cols-3 sm:w-auto">
        <TabsTrigger value="latest">最新动态</TabsTrigger>
        <TabsTrigger value="following" :disabled="!canUsePrivateFeeds">我的关注</TabsTrigger>
        <TabsTrigger value="groups" :disabled="!canUsePrivateFeeds">我的群组</TabsTrigger>
      </TabsList>
    </Tabs>

    <Card v-if="auth.isAuthenticated" class="border-white/70 bg-card/75 backdrop-blur-xl">
      <CardHeader>
        <CardTitle>动态公开偏好</CardTitle>
        <CardDescription>设置只影响未来产生的关注和加入群组动态，不追溯修改既有事件。</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div class="grid gap-3 sm:grid-cols-2">
          <div class="flex items-start gap-3">
            <Checkbox id="share-group-joins" v-model="preferences.share_group_joins" />
            <Label for="share-group-joins" class="font-normal leading-5">公开我加入公开群组的动态</Label>
          </div>
          <div class="flex items-start gap-3">
            <Checkbox id="share-follows" v-model="preferences.share_follows" />
            <Label for="share-follows" class="font-normal leading-5">公开我的关注动作</Label>
          </div>
        </div>
        <Button :disabled="savingPreferences" @click="savePreferences">
          {{ savingPreferences ? "保存中…" : "保存偏好" }}
        </Button>
      </CardContent>
    </Card>

    <div class="space-y-3">
      <Card
        v-for="item in items"
        :key="item.id"
        class="border-white/70 bg-card/75 shadow-sm backdrop-blur-xl"
      >
        <CardContent class="space-y-3 p-5">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div class="space-y-1">
              <p class="font-medium text-foreground">{{ activityTitle(item) }}</p>
              <p class="text-xs text-muted-foreground">{{ formatDate(item.created_at) }}</p>
            </div>
            <Badge variant="secondary">{{ item.kind.replaceAll("_", " ") }}</Badge>
          </div>
          <p class="rounded-xl bg-muted/60 p-3 text-sm leading-6 text-muted-foreground">
            {{ item.preview }}
          </p>
          <p v-if="item.post_title" class="text-sm font-medium text-foreground">
            主题：{{ item.post_title }}
          </p>
          <RouterLink
            v-if="activityLink(item)"
            :to="activityLink(item) ?? '/community'"
            class="inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            查看对应内容
          </RouterLink>
        </CardContent>
      </Card>

      <div
        v-if="!busy && items.length === 0"
        class="rounded-2xl border border-dashed border-border bg-card/60 p-10 text-center text-sm text-muted-foreground backdrop-blur-xl"
      >
        当前动态流暂无可展示事件。
      </div>

      <div v-if="hasMore" class="flex justify-center pt-2">
        <Button variant="outline" :disabled="loadingMore" @click="load(false)">
          {{ loadingMore ? "加载中…" : "加载更多" }}
        </Button>
      </div>
    </div>
  </section>
</template>
