<script setup lang="ts">
import type {
  CommunityBoard,
  CommunityBoardCode,
  CommunityPostDetail,
  CommunityPostSummary,
} from "@password-detective/api-contract";
import { computed, onMounted, ref, watch } from "vue";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createCommunityComment,
  createCommunityIdempotencyKey,
  createCommunityPost,
  getCommunityPost,
  listCommunityBoards,
  listCommunityPosts,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const boards = ref<CommunityBoard[]>([]);
const posts = ref<CommunityPostSummary[]>([]);
const selectedBoard = ref<CommunityBoardCode | undefined>();
const selectedPost = ref<CommunityPostDetail | null>(null);
const loading = ref(true);
const detailLoading = ref(false);
const submitting = ref(false);
const error = ref("");
const success = ref("");
const title = ref("");
const content = ref("");
const comment = ref("");
const rulesAccepted = ref(false);

const selectedBoardName = computed(() => {
  if (!selectedBoard.value) return "全部主题";
  return boards.value.find((board) => board.code === selectedBoard.value)?.name ?? "社区主题";
});
const canPublish = computed(
  () => auth.isAuthenticated && auth.user?.email_verified && rulesAccepted.value,
);

onMounted(async () => {
  await loadBoards();
  await loadPosts();
});

watch(selectedBoard, () => {
  void loadPosts();
});

async function loadBoards(): Promise<void> {
  try {
    boards.value = (await listCommunityBoards()).items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区分区加载失败";
  }
}

async function loadPosts(): Promise<void> {
  loading.value = true;
  try {
    const response = await listCommunityPosts(selectedBoard.value);
    posts.value = response.items;
    if (selectedPost.value && !posts.value.some((post) => post.id === selectedPost.value?.id)) {
      selectedPost.value = null;
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区主题加载失败";
  } finally {
    loading.value = false;
  }
}

async function openPost(post: CommunityPostSummary): Promise<void> {
  detailLoading.value = true;
  error.value = "";
  try {
    selectedPost.value = await getCommunityPost(post.id);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题详情加载失败";
  } finally {
    detailLoading.value = false;
  }
}

async function submitPost(): Promise<void> {
  if (!canPublish.value || title.value.trim().length < 4 || content.value.trim().length < 20) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    const created = await createCommunityPost(
      {
        board_code: selectedBoard.value ?? "general",
        title: title.value.trim(),
        content: content.value.trim(),
        rules_accepted: true,
      },
      auth.accessToken,
      createCommunityIdempotencyKey("post"),
    );
    title.value = "";
    content.value = "";
    rulesAccepted.value = false;
    selectedPost.value = created;
    success.value = "主题已发布，感谢你分享合成数据场景下的实践。";
    await loadPosts();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题发布失败";
  } finally {
    submitting.value = false;
  }
}

async function submitComment(): Promise<void> {
  if (!selectedPost.value || !canPublish.value || comment.value.trim().length < 2) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    selectedPost.value = await createCommunityComment(
      selectedPost.value.id,
      { content: comment.value.trim(), parent_id: null, rules_accepted: true },
      auth.accessToken,
      createCommunityIdempotencyKey("comment"),
    );
    comment.value = "";
    success.value = "回复已发布。";
    await loadPosts();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "回复发布失败";
  } finally {
    submitting.value = false;
  }
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function roleLabel(role: CommunityPostSummary["author"]["role"]): string {
  return {
    user: "成员",
    trusted_contributor: "可信贡献者",
    moderator: "版主",
    admin: "管理员",
    service: "服务账号",
  }[role];
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
            <Badge variant="secondary">验证后发言</Badge>
          </div>
          <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">社区协作中心</h1>
          <p class="text-muted-foreground">
            参考成熟论坛的分区、主题、回复和锁定机制，围绕授权数据安全地交流恢复经验。请勿发布真实密码、令牌或个人信息。
          </p>
        </div>
        <div class="rounded-xl bg-muted/50 p-4 text-sm text-muted-foreground">
          <div class="font-medium text-foreground">社区规则</div>
          <div class="mt-1">合成数据 · 最小披露 · 尊重协作 · 可追溯处理</div>
        </div>
      </div>
    </header>

    <Alert v-if="error" variant="destructive">
      <AlertTitle>操作未完成</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Alert v-if="success">
      <AlertTitle>操作成功</AlertTitle>
      <AlertDescription>{{ success }}</AlertDescription>
    </Alert>

    <div class="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <Card class="h-fit">
        <CardHeader>
          <CardTitle>社区分区</CardTitle>
          <CardDescription>按 Zibll 类论坛的信息架构拆分讨论边界。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-2">
          <Button
            class="h-auto w-full justify-between px-3 py-3 text-left"
            :variant="selectedBoard === undefined ? 'default' : 'ghost'"
            @click="selectedBoard = undefined"
          >
            <span>全部主题</span>
            <span class="text-xs opacity-75">{{ posts.length }}</span>
          </Button>
          <Button
            v-for="board in boards"
            :key="board.code"
            class="h-auto w-full items-start justify-between gap-3 px-3 py-3 text-left"
            :variant="selectedBoard === board.code ? 'default' : 'ghost'"
            @click="selectedBoard = board.code"
          >
            <span class="min-w-0">
              <span class="block font-medium">{{ board.name }}</span>
              <span class="mt-1 block text-xs font-normal opacity-75">{{ board.description }}</span>
            </span>
            <span class="text-xs opacity-75">{{ board.post_count }}</span>
          </Button>
        </CardContent>
      </Card>

      <div class="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.72fr)]">
        <Card>
          <CardHeader class="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>{{ selectedBoardName }}</CardTitle>
              <CardDescription>主题按置顶和最近活动排序，内容以纯文本安全展示。</CardDescription>
            </div>
            <Badge variant="outline">{{ posts.length }} 个主题</Badge>
          </CardHeader>
          <CardContent class="space-y-3">
            <div v-if="loading" class="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              正在加载社区主题…
            </div>
            <div v-else-if="posts.length === 0" class="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              这里还没有主题，欢迎从授权的合成数据经验开始分享。
            </div>
            <Button
              v-for="post in posts"
              v-else
              :key="post.id"
              class="h-auto w-full items-start justify-between gap-4 whitespace-normal px-4 py-4 text-left"
              :variant="selectedPost?.id === post.id ? 'secondary' : 'outline'"
              @click="openPost(post)"
            >
              <span class="min-w-0">
                <span class="flex flex-wrap items-center gap-2">
                  <Badge v-if="post.is_pinned" variant="secondary">置顶</Badge>
                  <span class="font-medium">{{ post.title }}</span>
                </span>
                <span class="mt-2 block line-clamp-3 text-sm font-normal text-muted-foreground">{{ post.content_preview }}</span>
                <span class="mt-3 block text-xs font-normal text-muted-foreground">
                  {{ post.author.username }} · {{ roleLabel(post.author.role) }} · {{ formatDate(post.last_activity_at) }}
                </span>
              </span>
              <span class="shrink-0 text-xs font-normal text-muted-foreground">{{ post.reply_count }} 回复</span>
            </Button>
          </CardContent>
        </Card>

        <div class="space-y-6">
          <Card v-if="selectedPost">
            <CardHeader>
              <div class="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{{ boards.find((board) => board.code === selectedPost?.board_code)?.name }}</Badge>
                <Badge v-if="selectedPost.is_locked" variant="outline">已锁定</Badge>
              </div>
              <CardTitle>{{ selectedPost.title }}</CardTitle>
              <CardDescription>{{ selectedPost.author.username }} · {{ formatDate(selectedPost.created_at) }}</CardDescription>
            </CardHeader>
            <CardContent class="space-y-5">
              <p class="whitespace-pre-wrap break-words text-sm leading-7">{{ selectedPost.content }}</p>
              <div class="space-y-3 border-t pt-4">
                <div class="flex items-center justify-between">
                  <h2 class="font-medium">回复（{{ selectedPost.comments.length }}）</h2>
                  <span v-if="detailLoading" class="text-xs text-muted-foreground">加载中…</span>
                </div>
                <div v-if="selectedPost.comments.length === 0" class="text-sm text-muted-foreground">还没有回复。</div>
                <div v-for="item in selectedPost.comments" :key="item.id" class="rounded-lg bg-muted/50 p-3">
                  <div class="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
                    <span>{{ item.author.username }} · {{ roleLabel(item.author.role) }}</span>
                    <span>{{ formatDate(item.created_at) }}</span>
                  </div>
                  <p class="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{{ item.content }}</p>
                </div>
              </div>
              <div v-if="auth.isAuthenticated && auth.user?.email_verified && !selectedPost.is_locked" class="space-y-3 border-t pt-4">
                <Label for="community-comment">写回复</Label>
                <Textarea id="community-comment" v-model="comment" placeholder="分享可复现、合法授权的经验…" :maxlength="2000" />
                <Button :disabled="submitting || comment.trim().length < 2" @click="submitComment">{{ submitting ? "发布中…" : "发布回复" }}</Button>
              </div>
              <p v-else-if="selectedPost.is_locked" class="text-sm text-muted-foreground">该主题已锁定，暂不接受新回复。</p>
              <p v-else class="text-sm text-muted-foreground">登录并完成邮箱验证后即可参与回复。</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>发布新主题</CardTitle>
              <CardDescription>首轮迁移仅开放主题与回复；私信、关注、点赞和复杂审核将在后续迭代中接入。</CardDescription>
            </CardHeader>
            <CardContent v-if="auth.isAuthenticated && auth.user?.email_verified" class="space-y-4">
              <div class="space-y-2">
                <Label for="community-title">主题标题</Label>
                <Input id="community-title" v-model="title" placeholder="例如：合成数据验证失败的排查记录" :maxlength="120" />
              </div>
              <div class="space-y-2">
                <Label for="community-content">主题内容</Label>
                <Textarea id="community-content" v-model="content" class="min-h-32" placeholder="请描述背景、已授权范围、复现步骤和结果…" :maxlength="5000" />
              </div>
              <div class="flex items-start gap-3">
                <Checkbox id="community-rules" v-model="rulesAccepted" />
                <Label for="community-rules" class="text-sm font-normal leading-5">我确认内容来自合法授权场景，不包含真实密码、令牌、密钥或个人信息。</Label>
              </div>
              <Button :disabled="submitting || title.trim().length < 4 || content.trim().length < 20 || !rulesAccepted" @click="submitPost">
                {{ submitting ? "发布中…" : "发布主题" }}
              </Button>
            </CardContent>
            <CardContent v-else>
              <p class="text-sm text-muted-foreground">登录并完成邮箱验证后即可发布主题。社区公开内容可直接浏览。</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  </section>
</template>
