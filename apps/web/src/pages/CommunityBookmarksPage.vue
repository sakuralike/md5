<script setup lang="ts">
import type { CommunityBookmarkItem } from "@password-detective/api-contract";
import { onMounted, onServerPrefetch, ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createCommunityIdempotencyKey,
  listCommunityBookmarks,
  setCommunityPostBookmark,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const items = ref<CommunityBookmarkItem[]>([]);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const loadingMore = ref(false);
const removingIds = ref(new Set<string>());
const error = ref("");

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

async function load(reset = true): Promise<void> {
  if (reset) loading.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const response = await listCommunityBookmarks(auth.accessToken, {
      cursor: reset ? undefined : (nextCursor.value ?? undefined),
      limit: 20,
    });
    items.value = reset ? response.items : [...items.value, ...response.items];
    nextCursor.value = response.next_cursor;
    hasMore.value = response.has_more;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载收藏列表";
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

async function remove(item: CommunityBookmarkItem): Promise<void> {
  if (removingIds.value.has(item.post_id)) return;
  removingIds.value = new Set(removingIds.value).add(item.post_id);
  error.value = "";
  try {
    await setCommunityPostBookmark(
      item.post_id,
      false,
      auth.accessToken,
      createCommunityIdempotencyKey("post-unbookmark"),
    );
    items.value = items.value.filter((candidate) => candidate.post_id !== item.post_id);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "取消收藏失败";
  } finally {
    const next = new Set(removingIds.value);
    next.delete(item.post_id);
    removingIds.value = next;
  }
}

onMounted(() => load());
onServerPrefetch(() => load());
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Saved discussions</p>
        <h1 class="text-3xl font-semibold tracking-tight text-foreground">我的社区收藏</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          收藏列表仅本人可见。主题失效后不展示正文，但仍可在此清理收藏引用。
        </p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load()">
        {{ loading ? "刷新中…" : "刷新" }}
      </Button>
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>收藏操作失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Card>
      <CardHeader>
        <CardTitle>已收藏主题</CardTitle>
        <CardDescription>按收藏时间倒序排列，不公开收藏者名单。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <article
          v-for="item in items"
          :key="item.post_id"
          class="space-y-3 rounded-xl border p-4"
        >
          <template v-if="item.post">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0 space-y-2">
                <div class="flex flex-wrap items-center gap-2">
                  <Badge>{{ item.post.board_code }}</Badge>
                  <Badge variant="secondary">{{ item.post.like_count }} 赞</Badge>
                </div>
                <h2 class="font-semibold text-foreground">{{ item.post.title }}</h2>
                <p class="line-clamp-2 text-sm leading-6 text-muted-foreground">
                  {{ item.post.content_preview }}
                </p>
                <p class="text-xs text-muted-foreground">
                  <RouterLink :to="`/community/users/${item.post.author.username}`" class="font-medium text-foreground hover:underline">
                    {{ item.post.author.username }}
                  </RouterLink>
                  · 收藏于 {{ formatDate(item.bookmarked_at) }}
                </p>
              </div>
              <div class="flex shrink-0 flex-wrap gap-2">
                <Button as-child size="sm">
                  <RouterLink :to="`/community/posts/${item.post_id}`">查看主题</RouterLink>
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  :disabled="removingIds.has(item.post_id)"
                  @click="remove(item)"
                >
                  {{ removingIds.has(item.post_id) ? "处理中…" : "取消收藏" }}
                </Button>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="space-y-1">
                <Badge variant="outline">内容已失效</Badge>
                <p class="text-sm text-muted-foreground">
                  该主题已被移除或不可访问，正文不会通过收藏列表泄露。
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                :disabled="removingIds.has(item.post_id)"
                @click="remove(item)"
              >
                {{ removingIds.has(item.post_id) ? "处理中…" : "清理收藏" }}
              </Button>
            </div>
          </template>
        </article>

        <div
          v-if="!loading && items.length === 0"
          class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground"
        >
          暂无收藏主题，可在社区主题详情页点击“收藏”。
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
