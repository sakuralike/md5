<script setup lang="ts">
import type { CommunityRelationUser } from "@password-detective/api-contract";
import { computed, onMounted, onServerPrefetch, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { listCommunityRelations } from "../services/community";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const auth = useAuthStore();
const items = ref<CommunityRelationUser[]>([]);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const loadingMore = ref(false);
const error = ref("");

const username = computed(() => String(route.params.username ?? ""));
const direction = computed<"followers" | "following">(() => route.meta.direction === "following" ? "following" : "followers");
const title = computed(() => direction.value === "followers" ? "关注者" : "正在关注");

async function load(reset = true): Promise<void> {
  if (!username.value) return;
  if (reset) loading.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const response = await listCommunityRelations(
      username.value,
      direction.value,
      auth.isAuthenticated ? auth.accessToken : undefined,
      reset ? undefined : (nextCursor.value ?? undefined),
    );
    items.value = reset ? response.items : [...items.value, ...response.items];
    nextCursor.value = response.next_cursor;
    hasMore.value = response.has_more;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载社区关系列表";
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

watch([username, direction], () => load());
onMounted(() => load());
onServerPrefetch(() => load());
</script>

<template>
  <section class="mx-auto max-w-4xl space-y-6">
    <header class="space-y-2">
      <Button as-child variant="ghost" size="sm"><RouterLink :to="`/community/users/${username}`">← 返回公开主页</RouterLink></Button>
      <h1 class="text-3xl font-semibold tracking-tight">@{{ username }} 的{{ title }}</h1>
      <p class="text-sm text-muted-foreground">仅展示状态正常且该用户允许公开的社区关系。</p>
    </header>
    <Alert v-if="error" variant="destructive"><AlertTitle>列表不可用</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
    <Card>
      <CardHeader><CardTitle>{{ title }}</CardTitle><CardDescription>邮箱、登录活动与设备信息不会出现在列表中。</CardDescription></CardHeader>
      <CardContent class="space-y-3">
        <div v-if="loading" class="h-32 animate-pulse rounded-xl bg-muted" />
        <RouterLink v-for="item in items" v-else :key="item.username" :to="`/community/users/${item.username}`" class="flex items-center gap-4 rounded-xl border p-4 hover:bg-muted/50">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary font-semibold text-primary-foreground">{{ item.display_name.slice(0, 1).toUpperCase() }}</div>
          <div class="min-w-0 flex-1"><p class="truncate font-medium">{{ item.display_name }}</p><p class="truncate text-sm text-muted-foreground">@{{ item.username }}</p></div>
          <Badge variant="outline">{{ item.level.name }}</Badge>
        </RouterLink>
        <p v-if="!loading && items.length === 0" class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">当前没有可显示的用户。</p>
        <div v-if="hasMore" class="flex justify-center"><Button variant="outline" :disabled="loadingMore" @click="load(false)">{{ loadingMore ? "加载中…" : "加载更多" }}</Button></div>
      </CardContent>
    </Card>
  </section>
</template>
