<script setup lang="ts">
import type { HashDetailResponse, HashVoteOutcome } from "@password-detective/api-contract";
import { computed, onMounted, onServerPrefetch, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { createClientId } from "@/lib/clientId";
import {
  createHashComment,
  getHashComments,
  getHashDetail,
  setHashCommentLike,
  setHashLike,
  voteHash,
} from "../services/hashDetails";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const auth = useAuthStore();
const detail = ref<HashDetailResponse | null>(null);
const loading = ref(true);
const busy = ref(false);
const commentsLoading = ref(false);
const error = ref("");
const success = ref("");
const comment = ref("");
const rulesAccepted = ref(false);

const algorithm = computed(() => String(route.params.algorithm ?? ""));
const digest = computed(() => String(route.params.digest ?? ""));
const isLoggedIn = computed(() => Boolean(auth.accessToken));
const commentCount = computed(() => detail.value?.comment_count ?? 0);

onMounted(() => void load());
onServerPrefetch(load);
watch(() => [route.params.algorithm, route.params.digest], () => void load());

async function load(): Promise<void> {
  if (!algorithm.value || !digest.value) return;
  loading.value = true;
  error.value = "";
  try {
    detail.value = await getHashDetail(algorithm.value, digest.value, auth.accessToken || undefined);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "哈希详情加载失败";
  } finally {
    loading.value = false;
  }
}

function requireLogin(): boolean {
  if (isLoggedIn.value) return true;
  error.value = "登录后才可以参与点赞、投票或评论";
  return false;
}

async function toggleLike(): Promise<void> {
  if (!detail.value || !requireLogin() || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await setHashLike(algorithm.value, digest.value, !detail.value.viewer_has_liked, auth.accessToken, key());
    detail.value = { ...detail.value, ...result };
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "点赞操作失败";
  } finally {
    busy.value = false;
  }
}

async function submitVote(outcome: HashVoteOutcome): Promise<void> {
  if (!detail.value || !requireLogin() || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await voteHash(algorithm.value, digest.value, outcome, auth.accessToken, key());
    detail.value = { ...detail.value, ...result };
    success.value = "你的评价已记录，可随时重新投票修正";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "投票失败";
  } finally {
    busy.value = false;
  }
}

async function toggleCommentLike(commentId: string, liked: boolean): Promise<void> {
  if (!detail.value || !requireLogin() || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const current = detail.value;
    const result = await setHashCommentLike(
      algorithm.value,
      digest.value,
      commentId,
      !liked,
      auth.accessToken,
      key(),
    );
    detail.value = {
      ...result,
      comment_count: current.comment_count,
      comments_next_cursor: current.comments_next_cursor,
      comments: current.comments.map((item) => item.id === commentId
        ? {
            ...item,
            viewer_has_liked: !liked,
            like_count: Math.max(0, item.like_count + (liked ? -1 : 1)),
          }
        : item),
    };
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "评论点赞失败";
  } finally {
    busy.value = false;
  }
}

async function loadMoreComments(): Promise<void> {
  if (!detail.value?.comments_next_cursor || commentsLoading.value) return;
  commentsLoading.value = true;
  error.value = "";
  try {
    const current = detail.value;
    const page = await getHashComments(
      algorithm.value,
      digest.value,
      current.comments_next_cursor,
      20,
      auth.accessToken || undefined,
    );
    const knownIds = new Set(current.comments.map((item) => item.id));
    detail.value = {
      ...current,
      comments: [
        ...current.comments,
        ...page.items.filter((item) => !knownIds.has(item.id)),
      ],
      comments_next_cursor: page.next_cursor,
    };
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "更多评论加载失败";
  } finally {
    commentsLoading.value = false;
  }
}

async function submitComment(): Promise<void> {
  if (!detail.value || !requireLogin() || busy.value || comment.value.trim().length < 2) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    detail.value = await createHashComment(
      algorithm.value,
      digest.value,
      { content: comment.value, rules_accepted: rulesAccepted.value },
      auth.accessToken,
      key(),
    );
    comment.value = "";
    rulesAccepted.value = false;
    success.value = "评论已发布";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "评论发布失败";
  } finally {
    busy.value = false;
  }
}

function key(): string {
  return `web-hash-${createClientId()}`;
}

function voteCount(outcome: HashVoteOutcome): number {
  return detail.value?.vote_counts[outcome] ?? 0;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
</script>

<template>
  <main class="min-h-screen bg-background px-4 py-10 text-foreground sm:px-6 lg:px-8">
    <div class="mx-auto max-w-5xl space-y-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" as-child><RouterLink to="/">返回首页</RouterLink></Button>
        <Button variant="outline" as-child><RouterLink to="/community">进入社区</RouterLink></Button>
      </div>

      <Alert v-if="error" variant="destructive"><AlertTitle>操作未完成</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
      <Alert v-if="success"><AlertTitle>已完成</AlertTitle><AlertDescription>{{ success }}</AlertDescription></Alert>

      <Card v-if="loading"><CardContent class="py-16 text-center text-muted-foreground">正在加载哈希详情…</CardContent></Card>
      <Card v-else-if="detail">
        <CardHeader class="space-y-4">
          <div class="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{{ detail.algorithm.toUpperCase() }}</Badge>
            <Badge v-if="detail.matched">已有档案</Badge>
            <Badge v-else variant="outline">暂无公开候选</Badge>
          </div>
          <div>
            <CardTitle class="text-2xl">哈希值详情</CardTitle>
            <CardDescription class="mt-2 break-all font-mono text-sm">{{ detail.digest }}</CardDescription>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" :disabled="busy" :aria-pressed="detail.viewer_has_liked" @click="toggleLike">
              {{ detail.viewer_has_liked ? "已点赞" : "点赞" }} · {{ detail.like_count }}
            </Button>
            <Button variant="outline" :disabled="busy" :aria-pressed="detail.viewer_vote === 'useful'" @click="submitVote('useful')">
              有帮助 · {{ voteCount('useful') }}
            </Button>
            <Button variant="outline" :disabled="busy" :aria-pressed="detail.viewer_vote === 'not_useful'" @click="submitVote('not_useful')">
              需核实 · {{ voteCount('not_useful') }}
            </Button>
            <span class="self-center text-sm text-muted-foreground">{{ commentCount }} 条评论</span>
          </div>
        </CardHeader>
        <CardContent class="space-y-6">
          <section v-if="detail.archive" class="grid gap-3 sm:grid-cols-3">
            <div class="rounded-lg border bg-muted/20 p-4"><p class="text-xs text-muted-foreground">候选数量</p><p class="mt-1 text-xl font-semibold">{{ detail.archive.candidate_count }}</p></div>
            <div class="rounded-lg border bg-muted/20 p-4"><p class="text-xs text-muted-foreground">文件格式</p><p class="mt-1 text-xl font-semibold">{{ detail.archive.optional_format?.toUpperCase() ?? "未记录" }}</p></div>
            <div class="rounded-lg border bg-muted/20 p-4"><p class="text-xs text-muted-foreground">文件大小</p><p class="mt-1 text-xl font-semibold">{{ detail.archive.optional_size ? `${detail.archive.optional_size} bytes` : "未记录" }}</p></div>
          </section>

          <section v-if="detail.archive" class="space-y-3">
            <h2 class="text-lg font-semibold">公开候选（仅显示脱敏信息）</h2>
            <div v-for="candidate in detail.archive.candidates" :key="candidate.id" class="rounded-lg border p-4">
              <div class="flex flex-wrap items-center justify-between gap-2"><span class="font-mono">{{ candidate.masked_secret }}</span><Badge variant="outline">{{ candidate.status }}</Badge></div>
              <p class="mt-2 text-sm text-muted-foreground">贡献 {{ candidate.submission_count }} 条 · 成功证据 {{ candidate.success_evidence_count }} 条 · 失败证据 {{ candidate.failure_evidence_count }} 条</p>
            </div>
          </section>

          <section class="space-y-4">
            <div><h2 class="text-lg font-semibold">评论与讨论</h2><p class="text-sm text-muted-foreground">请勿发布明文密码、令牌或未经授权的敏感数据。</p></div>
            <div v-if="isLoggedIn" class="space-y-3 rounded-lg border bg-muted/20 p-4">
              <Textarea v-model="comment" maxlength="2000" placeholder="分享验证过程或补充说明…" />
              <div class="flex flex-wrap items-center justify-between gap-3">
                <label class="flex items-center gap-2 text-sm text-muted-foreground"><Checkbox v-model="rulesAccepted" />我确认遵守社区规则</label>
                <Button :disabled="busy || !rulesAccepted || comment.trim().length < 2" @click="submitComment">发布评论</Button>
              </div>
            </div>
            <div v-else class="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">登录后可以发表评论和参与互动。<Button variant="link" as-child class="px-1"><RouterLink to="/login">立即登录</RouterLink></Button></div>
            <div v-if="detail.comments.length" class="space-y-3">
              <article v-for="item in detail.comments" :key="item.id" class="rounded-lg border p-4">
                <div class="flex items-center justify-between gap-3"><span class="font-medium">{{ item.author.username }}</span><time class="text-xs text-muted-foreground">{{ formatDate(item.created_at) }}</time></div>
                <p class="mt-2 whitespace-pre-wrap text-sm leading-6">{{ item.content }}</p>
                <Button
                  variant="ghost"
                  size="sm"
                  class="mt-3 px-0 text-xs text-muted-foreground"
                  :disabled="busy || !isLoggedIn"
                  :aria-pressed="item.viewer_has_liked"
                  @click="toggleCommentLike(item.id, item.viewer_has_liked)"
                >
                  {{ item.viewer_has_liked ? "已点赞" : "点赞" }} {{ item.like_count }}
                </Button>
              </article>
            </div>
            <p v-else class="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">还没有评论，欢迎成为第一位贡献者。</p>
            <Button
              v-if="detail.comments_next_cursor"
              variant="outline"
              class="w-full"
              :disabled="commentsLoading"
              @click="loadMoreComments"
            >
              {{ commentsLoading ? "加载中…" : "加载更多评论" }}
            </Button>
          </section>
        </CardContent>
      </Card>
    </div>
  </main>
</template>
