<script setup lang="ts">
import type { CommunityCommentResponse, CommunityPostDetail } from "@password-detective/api-contract";
import { onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { createCommunityComment, createCommunityIdempotencyKey, getCommunityPost, listCommunityComments } from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const post = ref<CommunityPostDetail | null>(null);
const comments = ref<CommunityCommentResponse[]>([]);
const nextCursor = ref<string | null>(null);
const comment = ref("");
const rulesAccepted = ref(false);
const replyParent = ref<CommunityCommentResponse | null>(null);
const loading = ref(true);
const commentsLoading = ref(false);
const submitting = ref(false);
const error = ref("");

onMounted(() => void load());
watch(() => route.params.postId, () => void load());

async function load(): Promise<void> {
  const postId = typeof route.params.postId === "string" ? route.params.postId : "";
  if (!postId) return;
  loading.value = true;
  error.value = "";
  try {
    const [detail, page] = await Promise.all([getCommunityPost(postId), listCommunityComments(postId)]);
    post.value = detail;
    comments.value = page.items;
    nextCursor.value = page.next_cursor;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题详情加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadMore(): Promise<void> {
  if (!post.value || !nextCursor.value || commentsLoading.value) return;
  commentsLoading.value = true;
  try {
    const page = await listCommunityComments(post.value.id, nextCursor.value);
    comments.value = [...comments.value, ...page.items];
    nextCursor.value = page.next_cursor;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "更多回复加载失败";
  } finally {
    commentsLoading.value = false;
  }
}

async function submitComment(): Promise<void> {
  if (!post.value || !auth.isAuthenticated || !auth.user?.email_verified || !rulesAccepted.value || comment.value.trim().length < 2) return;
  submitting.value = true;
  error.value = "";
  try {
    await createCommunityComment(
      post.value.id,
      { content: comment.value.trim(), parent_id: replyParent.value?.id ?? null, rules_accepted: true },
      auth.accessToken,
      createCommunityIdempotencyKey("comment"),
    );
    comment.value = "";
    rulesAccepted.value = false;
    replyParent.value = null;
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "回复发布失败";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <section class="mx-auto w-full max-w-4xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <Button variant="outline" as-child><RouterLink to="/community">← 返回社区首页</RouterLink></Button>
      <Button variant="outline" as-child><RouterLink to="/community/new">发布新主题</RouterLink></Button>
    </div>
    <Alert v-if="error" variant="destructive">
      <AlertTitle>加载失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Card v-if="loading"><CardContent class="p-8 text-center text-sm text-muted-foreground">正在加载主题…</CardContent></Card>
    <template v-else-if="post">
      <Card>
        <CardHeader>
          <div class="flex flex-wrap items-center gap-2">
            <Badge>{{ post.board_code }}</Badge>
            <Badge v-if="post.is_locked" variant="outline">已锁定</Badge>
            <Badge v-if="post.edited_at" variant="secondary">已编辑</Badge>
          </div>
          <CardTitle class="text-2xl">{{ post.title }}</CardTitle>
          <CardDescription>{{ post.author.username }} · {{ new Date(post.created_at).toLocaleString() }}</CardDescription>
        </CardHeader>
        <CardContent>
          <p class="whitespace-pre-wrap break-words text-sm leading-7">{{ post.content }}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>评论和回复</CardTitle><CardDescription>{{ post.reply_count }} 条回复，支持两级定向回复。</CardDescription></CardHeader>
        <CardContent class="space-y-4">
          <div v-if="comments.length === 0" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">还没有回复。</div>
          <article v-for="item in comments" :key="item.id" class="rounded-lg border p-4" :class="{ 'ml-6': item.parent_id }">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="text-sm font-medium">{{ item.author.username }}<span v-if="item.reply_to_user_id" class="ml-2 text-xs text-muted-foreground">定向回复</span></div>
              <span class="text-xs text-muted-foreground">{{ new Date(item.created_at).toLocaleString() }}</span>
            </div>
            <p class="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{{ item.content }}</p>
            <Button v-if="auth.isAuthenticated && !post.is_locked" variant="ghost" size="sm" class="mt-2" @click="replyParent = item">回复</Button>
          </article>
          <Button v-if="nextCursor" variant="outline" class="w-full" :disabled="commentsLoading" @click="loadMore">{{ commentsLoading ? "加载中…" : "加载更多回复" }}</Button>
          <div v-if="auth.isAuthenticated && auth.user?.email_verified && !post.is_locked" class="space-y-3 border-t pt-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <Label for="community-post-comment">{{ replyParent ? `回复 ${replyParent.author.username}` : "写回复" }}</Label>
              <Button v-if="replyParent" variant="ghost" size="sm" @click="replyParent = null">取消定向回复</Button>
            </div>
            <Textarea id="community-post-comment" v-model="comment" :maxlength="2000" placeholder="分享可复现、合法授权的经验…" />
            <div class="flex items-start gap-3"><Checkbox id="community-post-rules" v-model="rulesAccepted" /><Label for="community-post-rules" class="text-sm font-normal leading-5">我确认回复不包含真实密码、令牌、密钥或个人信息。</Label></div>
            <Button :disabled="submitting || comment.trim().length < 2 || !rulesAccepted" @click="submitComment">{{ submitting ? "发布中…" : "发布回复" }}</Button>
          </div>
          <p v-else-if="post.is_locked" class="text-sm text-muted-foreground">该主题已锁定，暂不接受新回复。</p>
          <p v-else class="text-sm text-muted-foreground">登录并完成邮箱验证后即可参与回复。</p>
        </CardContent>
      </Card>
    </template>
  </section>
</template>
