<script setup lang="ts">
import type { CommunityBoard, CommunityBoardCode, CommunityPostSummary } from "@password-detective/api-contract";
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCommunityHome } from "../services/community";

const route = useRoute();
const router = useRouter();
const boards = ref<CommunityBoard[]>([]);
const posts = ref<CommunityPostSummary[]>([]);
const selectedBoard = ref<CommunityBoardCode | undefined>(readBoard(route.query.board));
const loading = ref(true);
const error = ref("");

const selectedBoardName = computed(() => {
  if (!selectedBoard.value) return "全部主题";
  return boards.value.find((board) => board.code === selectedBoard.value)?.name ?? "社区主题";
});

onMounted(async () => {
  await loadHome();
});

watch(
  () => route.query.board,
  (value) => {
    selectedBoard.value = readBoard(value);
    void loadHome();
  },
);

function readBoard(value: unknown): CommunityBoardCode | undefined {
  if (typeof value !== "string") return undefined;
  const valid: CommunityBoardCode[] = ["general", "recovery_guides", "verification", "security"];
  return valid.includes(value as CommunityBoardCode) ? (value as CommunityBoardCode) : undefined;
}

async function loadHome(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await getCommunityHome(selectedBoard.value);
    boards.value = response.boards;
    posts.value = response.posts.items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区首页加载失败";
  } finally {
    loading.value = false;
  }
}

async function selectBoard(code?: CommunityBoardCode): Promise<void> {
  await router.push({
    path: "/community",
    query: code ? { board: code } : {},
  });
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}
</script>

<template>
  <section class="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
    <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div class="max-w-3xl space-y-3">
          <div class="flex flex-wrap items-center gap-2">
            <Badge>社区协作</Badge>
            <Badge variant="secondary">公开阅读</Badge>
            <Badge variant="outline">首页</Badge>
          </div>
          <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">社区首页</h1>
          <p class="text-muted-foreground">
            按板块浏览合成数据、验证流程和安全实践。帖子详情、评论和发布均使用独立页面，便于分享和返回。
          </p>
        </div>
        <Button as-child>
          <RouterLink to="/community/new">发布新主题</RouterLink>
        </Button>
      </div>
    </header>

    <Alert v-if="error" variant="destructive">
      <AlertTitle>社区暂时不可用</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <div class="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <Card class="h-fit">
        <CardHeader>
          <CardTitle>社区板块</CardTitle>
          <CardDescription>选择讨论边界。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-2">
          <Button
            class="w-full justify-start"
            :variant="selectedBoard ? 'ghost' : 'secondary'"
            @click="selectBoard()"
          >
            全部主题
          </Button>
          <Button
            v-for="board in boards"
            :key="board.code"
            class="h-auto w-full justify-start whitespace-normal py-3 text-left"
            :variant="selectedBoard === board.code ? 'secondary' : 'ghost'"
            @click="selectBoard(board.code)"
          >
            <span class="space-y-1">
              <span class="block font-medium">{{ board.name }}</span>
              <span class="block text-xs text-muted-foreground">{{ board.post_count }} 个主题</span>
            </span>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>{{ selectedBoardName }}</CardTitle>
            <CardDescription>按置顶和最近活动排序，点击主题进入独立详情页。</CardDescription>
          </div>
          <Button variant="outline" @click="loadHome">刷新</Button>
        </CardHeader>
        <CardContent class="space-y-3">
          <div v-if="loading" class="space-y-3">
            <div v-for="index in 4" :key="index" class="h-24 w-full animate-pulse rounded-xl bg-muted" />
          </div>
          <div v-else-if="posts.length === 0" class="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            当前板块还没有公开主题，欢迎发布第一个讨论。
          </div>
          <template v-else>
            <RouterLink
              v-for="post in posts"
              :key="post.id"
              class="block rounded-xl border p-4 transition-colors hover:bg-muted/50"
              :to="`/community/posts/${post.id}`"
            >
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0 space-y-2">
                  <div class="flex flex-wrap items-center gap-2">
                    <Badge v-if="post.is_pinned" variant="secondary">置顶</Badge>
                    <Badge v-if="post.is_locked" variant="outline">已锁定</Badge>
                    <h2 class="truncate text-base font-semibold">{{ post.title }}</h2>
                  </div>
                  <p class="line-clamp-2 text-sm text-muted-foreground">{{ post.content_preview }}</p>
                  <p class="text-xs text-muted-foreground">
                    {{ post.author.username }} · {{ post.reply_count }} 条回复 · {{ formatDate(post.last_activity_at) }}
                  </p>
                </div>
                <span class="shrink-0 text-sm text-primary">查看详情 →</span>
              </div>
            </RouterLink>
          </template>
        </CardContent>
      </Card>
    </div>
  </section>
</template>
