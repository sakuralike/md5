<script setup lang="ts">
import type {
  CommunityCommentResponse,
  CommunityPostDetail,
  CommunityReportReason,
} from "@password-detective/api-contract";
import { computed, onMounted, onServerPrefetch, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createCommunityComment,
  createCommunityIdempotencyKey,
  createCommunityReport,
  deleteCommunityComment,
  deleteCommunityPost,
  getCommunityPost,
  listCommunityComments,
  setCommunityCommentLike,
  setCommunityPostBookmark,
  setCommunityPostLike,
  updateCommunityComment,
  updateCommunityPost,
  updateCommunityPostSeo,
} from "../services/community";
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
const success = ref("");
const editingPost = ref(false);
const editTitle = ref("");
const editContent = ref("");
const editingSeo = ref(false);
const seoTitle = ref("");
const seoDescription = ref("");
const seoKeywords = ref("");
const seoCanonicalPath = ref("");
const seoOgImageUrl = ref("");
const editingCommentId = ref<string | null>(null);
const editCommentContent = ref("");
const postDeleteArmed = ref(false);
const commentDeleteArmed = ref<string | null>(null);
const reportTarget = ref<{ type: "post" | "comment"; commentId: string | null } | null>(null);
const reportReason = ref<CommunityReportReason>("other");
const reportDetails = ref("");
const postInteractionBusy = ref(false);
const commentLikeBusyIds = ref(new Set<string>());

const isPostAuthor = computed(
  () => Boolean(auth.user && post.value?.author.user_id === auth.user.id),
);
const canEditPostSeo = computed(() => Boolean(
  auth.user
  && post.value
  && (post.value.author.user_id === auth.user.id || ["moderator", "admin"].includes(auth.user.role)),
));

onMounted(() => void load());
onServerPrefetch(load);
watch(() => route.params.postId, () => void load());

async function load(): Promise<void> {
  const postId = typeof route.params.postId === "string" ? route.params.postId : "";
  if (!postId) return;
  loading.value = true;
  error.value = "";
  try {
    const [detail, page] = await Promise.all([
      getCommunityPost(postId, auth.accessToken || undefined),
      listCommunityComments(postId, undefined, 20, auth.accessToken || undefined),
    ]);
    post.value = detail;
    comments.value = page.items;
    nextCursor.value = page.next_cursor;
    resetDetailForms();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题详情加载失败";
  } finally {
    loading.value = false;
  }
}

async function refresh(): Promise<void> {
  if (!post.value) return;
  const [detail, page] = await Promise.all([
    getCommunityPost(post.value.id, auth.accessToken || undefined),
    listCommunityComments(post.value.id, undefined, 20, auth.accessToken || undefined),
  ]);
  post.value = detail;
  comments.value = page.items;
  nextCursor.value = page.next_cursor;
}

async function loadMore(): Promise<void> {
  if (!post.value || !nextCursor.value || commentsLoading.value) return;
  commentsLoading.value = true;
  try {
    const page = await listCommunityComments(
      post.value.id,
      nextCursor.value,
      20,
      auth.accessToken || undefined,
    );
    comments.value = [...comments.value, ...page.items];
    nextCursor.value = page.next_cursor;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "更多回复加载失败";
  } finally {
    commentsLoading.value = false;
  }
}

function requireInteractionLogin(): boolean {
  if (auth.isAuthenticated) return true;
  error.value = "登录后才能点赞或收藏社区内容";
  return false;
}

async function togglePostLike(): Promise<void> {
  if (!post.value || postInteractionBusy.value || !requireInteractionLogin()) return;
  postInteractionBusy.value = true;
  error.value = "";
  try {
    const nextLiked = !post.value.viewer_has_liked;
    const response = await setCommunityPostLike(
      post.value.id,
      nextLiked,
      auth.accessToken,
      createCommunityIdempotencyKey(nextLiked ? "post-like" : "post-unlike"),
    );
    post.value.like_count = response.like_count;
    post.value.viewer_has_liked = response.viewer_has_liked;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题点赞操作失败";
  } finally {
    postInteractionBusy.value = false;
  }
}

async function togglePostBookmark(): Promise<void> {
  if (!post.value || postInteractionBusy.value || !requireInteractionLogin()) return;
  postInteractionBusy.value = true;
  error.value = "";
  try {
    const nextBookmarked = !post.value.viewer_has_bookmarked;
    const response = await setCommunityPostBookmark(
      post.value.id,
      nextBookmarked,
      auth.accessToken,
      createCommunityIdempotencyKey(
        nextBookmarked ? "post-bookmark" : "post-unbookmark",
      ),
    );
    post.value.viewer_has_bookmarked = response.viewer_has_bookmarked;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题收藏操作失败";
  } finally {
    postInteractionBusy.value = false;
  }
}

async function toggleCommentLike(item: CommunityCommentResponse): Promise<void> {
  if (commentLikeBusyIds.value.has(item.id) || !requireInteractionLogin()) return;
  commentLikeBusyIds.value = new Set(commentLikeBusyIds.value).add(item.id);
  error.value = "";
  try {
    const nextLiked = !item.viewer_has_liked;
    const response = await setCommunityCommentLike(
      item.id,
      nextLiked,
      auth.accessToken,
      createCommunityIdempotencyKey(nextLiked ? "comment-like" : "comment-unlike"),
    );
    item.like_count = response.like_count;
    item.viewer_has_liked = response.viewer_has_liked;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "回复点赞操作失败";
  } finally {
    const next = new Set(commentLikeBusyIds.value);
    next.delete(item.id);
    commentLikeBusyIds.value = next;
  }
}

function beginPostEdit(): void {
  if (!post.value || !isPostAuthor.value) return;
  editingPost.value = true;
  editTitle.value = post.value.title;
  editContent.value = post.value.content;
  postDeleteArmed.value = false;
  error.value = "";
}

async function savePostEdit(): Promise<void> {
  if (!post.value || !isPostAuthor.value || editTitle.value.trim().length < 4 || editContent.value.trim().length < 20) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    const postId = post.value.id;
    await updateCommunityPost(
      postId,
      {
        title: editTitle.value.trim(),
        content: editContent.value.trim(),
        rules_accepted: true,
        expected_version: post.value.version,
      },
      auth.accessToken,
      createCommunityIdempotencyKey("post-update"),
    );
    await refresh();
    editingPost.value = false;
    postDeleteArmed.value = false;
    success.value = "主题修改已保存。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题修改失败";
  } finally {
    submitting.value = false;
  }
}

function loadSeoForm(): void {
  if (!post.value) return;
  seoTitle.value = post.value.seo_title ?? "";
  seoDescription.value = post.value.seo_description ?? "";
  seoKeywords.value = (post.value.seo_keywords ?? []).join(", ");
  seoCanonicalPath.value = post.value.seo_canonical_path ?? "";
  seoOgImageUrl.value = post.value.og_image_url ?? "";
}

function beginSeoEdit(): void {
  if (!post.value || !canEditPostSeo.value) return;
  loadSeoForm();
  editingSeo.value = true;
  error.value = "";
}

function resetSeoForm(): void {
  loadSeoForm();
  error.value = "";
}

function normalizedOptional(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function normalizedSeoKeywords(): string[] | null {
  const values = seoKeywords.value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index);
  return values.length ? values : null;
}

async function saveSeoEdit(): Promise<void> {
  if (!post.value || !canEditPostSeo.value) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    post.value = await updateCommunityPostSeo(
      post.value.id,
      {
        seo_title: normalizedOptional(seoTitle.value),
        seo_description: normalizedOptional(seoDescription.value),
        seo_keywords: normalizedSeoKeywords(),
        seo_canonical_path: normalizedOptional(seoCanonicalPath.value),
        og_image_url: normalizedOptional(seoOgImageUrl.value),
        expected_seo_version: post.value.seo_version,
      },
      auth.accessToken,
      createCommunityIdempotencyKey("post-seo-update"),
    );
    editingSeo.value = false;
    success.value = "主题 SEO 设置已保存。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题 SEO 设置保存失败";
  } finally {
    submitting.value = false;
  }
}

async function removePost(): Promise<void> {
  if (!post.value || !isPostAuthor.value) return;
  if (!postDeleteArmed.value) {
    postDeleteArmed.value = true;
    return;
  }
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    const postId = post.value.id;
    await deleteCommunityPost(
      postId,
      post.value.version,
      auth.accessToken,
      createCommunityIdempotencyKey("post-delete"),
    );
    await refresh();
    editingPost.value = false;
    postDeleteArmed.value = false;
    success.value = "主题正文已删除并保留结构占位。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题删除失败";
  } finally {
    submitting.value = false;
  }
}

async function submitComment(): Promise<void> {
  if (!post.value || !auth.isAuthenticated || !auth.user?.email_verified || !rulesAccepted.value || comment.value.trim().length < 2) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
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
    await refresh();
    success.value = "回复已发布。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "回复发布失败";
  } finally {
    submitting.value = false;
  }
}

function beginCommentEdit(item: CommunityCommentResponse): void {
  if (item.author.user_id !== auth.user?.id || item.content.startsWith("该回复已由作者删除")) return;
  editingCommentId.value = item.id;
  editCommentContent.value = item.content;
  commentDeleteArmed.value = null;
  error.value = "";
}

async function saveCommentEdit(item: CommunityCommentResponse): Promise<void> {
  if (!post.value || item.author.user_id !== auth.user?.id || editCommentContent.value.trim().length < 2) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    await updateCommunityComment(
      item.id,
      {
        content: editCommentContent.value.trim(),
        rules_accepted: true,
        expected_version: item.version,
      },
      auth.accessToken,
      createCommunityIdempotencyKey("comment-update"),
    );
    await refresh();
    editingCommentId.value = null;
    success.value = "回复修改已保存。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "回复修改失败";
  } finally {
    submitting.value = false;
  }
}

async function removeComment(item: CommunityCommentResponse): Promise<void> {
  if (!post.value || item.author.user_id !== auth.user?.id || item.content.startsWith("该回复已由作者删除")) return;
  if (commentDeleteArmed.value !== item.id) {
    commentDeleteArmed.value = item.id;
    return;
  }
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    await deleteCommunityComment(
      item.id,
      item.version,
      auth.accessToken,
      createCommunityIdempotencyKey("comment-delete"),
    );
    await refresh();
    commentDeleteArmed.value = null;
    success.value = "回复正文已删除并保留结构占位。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "回复删除失败";
  } finally {
    submitting.value = false;
  }
}

function beginReport(type: "post" | "comment", commentId: string | null = null): void {
  if (!auth.isAuthenticated || !auth.user?.email_verified) return;
  reportTarget.value = { type, commentId };
  reportReason.value = "other";
  reportDetails.value = "";
  error.value = "";
  success.value = "";
}

async function submitReport(): Promise<void> {
  if (!post.value || !reportTarget.value || !auth.isAuthenticated || !auth.user?.email_verified || reportDetails.value.trim().length < 10) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    await createCommunityReport(
      {
        post_id: post.value.id,
        comment_id: reportTarget.value.commentId,
        reason: reportReason.value,
        details: reportDetails.value.trim(),
      },
      auth.accessToken,
      createCommunityIdempotencyKey("report"),
    );
    reportTarget.value = null;
    reportDetails.value = "";
    success.value = "举报已提交，社区治理人员会在管理端复核。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "举报提交失败";
  } finally {
    submitting.value = false;
  }
}

function resetDetailForms(): void {
  reportTarget.value = null;
  reportDetails.value = "";
  replyParent.value = null;
  rulesAccepted.value = false;
  editingPost.value = false;
  editingSeo.value = false;
  editingCommentId.value = null;
  postDeleteArmed.value = false;
  commentDeleteArmed.value = null;
}

function reportReasonLabel(reason: CommunityReportReason): string {
  return {
    spam: "垃圾广告",
    harassment: "骚扰攻击",
    privacy: "隐私泄露",
    unsafe: "不安全内容",
    other: "其他问题",
  }[reason];
}
</script>

<template>
  <section class="mx-auto w-full max-w-4xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <Button variant="outline" as-child><RouterLink to="/community">← 返回社区首页</RouterLink></Button>
      <Button variant="outline" as-child><RouterLink to="/community/new">发布新主题</RouterLink></Button>
    </div>
    <Alert v-if="error" variant="destructive">
      <AlertTitle>操作失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Alert v-if="success">
      <AlertTitle>操作完成</AlertTitle>
      <AlertDescription>{{ success }}</AlertDescription>
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
          <div v-if="editingPost" class="space-y-3">
            <div class="space-y-2">
              <Label for="community-post-edit-title">主题标题</Label>
              <Input id="community-post-edit-title" v-model="editTitle" :maxlength="120" />
            </div>
            <div class="space-y-2">
              <Label for="community-post-edit-content">主题内容</Label>
              <Textarea id="community-post-edit-content" v-model="editContent" class="min-h-40" :maxlength="10000" />
            </div>
            <div class="flex flex-wrap gap-2">
              <Button :disabled="submitting || editTitle.trim().length < 4 || editContent.trim().length < 20" @click="savePostEdit">保存修改</Button>
              <Button variant="outline" @click="editingPost = false">取消编辑</Button>
            </div>
          </div>
          <template v-else>
            <CardTitle class="text-2xl">{{ post.title }}</CardTitle>
            <CardDescription>
              <RouterLink :to="`/community/users/${post.author.username}`" class="font-medium text-foreground hover:underline">
                {{ post.author.username }}
              </RouterLink>
              · {{ new Date(post.created_at).toLocaleString() }}
            </CardDescription>
            <div class="flex flex-wrap gap-2 pt-2">
              <Button v-if="isPostAuthor && !post.content.startsWith('该主题正文已删除')" size="sm" variant="outline" @click="beginPostEdit">编辑主题</Button>
              <Button v-if="isPostAuthor && !post.content.startsWith('该主题正文已删除')" size="sm" variant="destructive" :disabled="submitting" @click="removePost">{{ postDeleteArmed ? "再次确认删除" : "删除主题" }}</Button>
              <Button v-if="auth.isAuthenticated && auth.user?.email_verified" size="sm" variant="ghost" @click="beginReport('post')">举报主题</Button>
              <Button
                size="sm"
                :variant="post.viewer_has_liked ? 'default' : 'outline'"
                :disabled="postInteractionBusy"
                @click="togglePostLike"
              >
                {{ post.viewer_has_liked ? "已点赞" : "点赞" }} {{ post.like_count }}
              </Button>
              <Button
                size="sm"
                :variant="post.viewer_has_bookmarked ? 'secondary' : 'outline'"
                :disabled="postInteractionBusy"
                @click="togglePostBookmark"
              >
                {{ post.viewer_has_bookmarked ? "已收藏" : "收藏" }}
              </Button>
            </div>
          </template>
        </CardHeader>
        <CardContent>
          <p v-if="!editingPost" class="whitespace-pre-wrap break-words text-sm leading-7">{{ post.content }}</p>
        </CardContent>
      </Card>
      <Card v-if="canEditPostSeo">
        <CardHeader>
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="space-y-1">
              <CardTitle>SEO 设置</CardTitle>
              <CardDescription>为主题配置搜索标题、摘要、关键词、站内规范路径和分享图片。动态内容仍保持不索引。</CardDescription>
            </div>
            <Button v-if="!editingSeo" size="sm" variant="outline" @click="beginSeoEdit">编辑 SEO</Button>
          </div>
        </CardHeader>
        <CardContent class="space-y-4">
          <div v-if="editingSeo" class="space-y-4">
            <div class="space-y-2">
              <Label for="community-post-seo-title">搜索标题</Label>
              <Input id="community-post-seo-title" v-model="seoTitle" :maxlength="120" :placeholder="post.title" />
              <p class="text-xs text-muted-foreground">留空时使用主题标题，最多 120 个字符。</p>
            </div>
            <div class="space-y-2">
              <Label for="community-post-seo-description">搜索摘要</Label>
              <Textarea id="community-post-seo-description" v-model="seoDescription" :maxlength="320" :placeholder="post.seo.description" />
              <p class="text-xs text-muted-foreground">留空时使用安全正文摘要，最多 320 个字符。</p>
            </div>
            <div class="space-y-2">
              <Label for="community-post-seo-keywords">关键词</Label>
              <Input id="community-post-seo-keywords" v-model="seoKeywords" placeholder="例如：压缩包, 密码恢复, 安全教程" />
              <p class="text-xs text-muted-foreground">使用逗号或换行分隔；保存时自动去重和去除空白。</p>
            </div>
            <div class="space-y-2">
              <Label for="community-post-seo-canonical">站内规范路径</Label>
              <Input id="community-post-seo-canonical" v-model="seoCanonicalPath" :maxlength="512" :placeholder="post.seo.canonical_path ?? `/community/posts/${post.id}`" />
              <p class="text-xs text-muted-foreground">仅允许不带查询参数或片段的站内绝对路径。</p>
            </div>
            <div class="space-y-2">
              <Label for="community-post-seo-og-image">分享图片地址</Label>
              <Input id="community-post-seo-og-image" v-model="seoOgImageUrl" :maxlength="1024" placeholder="/assets/community/default-share.png 或 HTTPS 地址" />
            </div>
            <div class="flex flex-wrap gap-2">
              <Button :disabled="submitting" @click="saveSeoEdit">{{ submitting ? "保存中…" : "保存 SEO" }}</Button>
              <Button variant="outline" :disabled="submitting" @click="resetSeoForm">重置</Button>
              <Button variant="ghost" :disabled="submitting" @click="editingSeo = false">取消</Button>
            </div>
          </div>
          <div v-else class="grid gap-3 text-sm sm:grid-cols-2">
            <div><span class="text-muted-foreground">搜索标题：</span>{{ post.seo.title }}</div>
            <div><span class="text-muted-foreground">SEO 版本：</span>{{ post.seo_version }}</div>
            <div class="sm:col-span-2"><span class="text-muted-foreground">规范路径：</span>{{ post.seo.canonical_path ?? "未设置" }}</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>评论和回复</CardTitle><CardDescription>{{ post.reply_count }} 条回复，支持两级定向回复。</CardDescription></CardHeader>
        <CardContent class="space-y-4">
          <div v-if="comments.length === 0" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">还没有回复。</div>
          <article v-for="item in comments" :key="item.id" class="rounded-lg border p-4" :class="{ 'ml-6': item.parent_id }">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="text-sm font-medium">
                <RouterLink :to="`/community/users/${item.author.username}`" class="hover:underline">
                  {{ item.author.username }}
                </RouterLink>
                <span v-if="item.reply_to_user_id" class="ml-2 text-xs text-muted-foreground">定向回复</span>
              </div>
              <span class="text-xs text-muted-foreground">{{ new Date(item.created_at).toLocaleString() }}</span>
            </div>
            <div v-if="editingCommentId === item.id" class="mt-3 space-y-3">
              <Label :for="`community-comment-edit-${item.id}`">编辑回复</Label>
              <Textarea :id="`community-comment-edit-${item.id}`" v-model="editCommentContent" :maxlength="2000" />
              <div class="flex flex-wrap gap-2">
                <Button size="sm" :disabled="submitting || editCommentContent.trim().length < 2" @click="saveCommentEdit(item)">保存回复</Button>
                <Button size="sm" variant="outline" @click="editingCommentId = null">取消</Button>
              </div>
            </div>
            <p v-else class="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{{ item.content }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Button v-if="auth.isAuthenticated && auth.user?.email_verified && !post.is_locked" size="sm" variant="ghost" @click="replyParent = item">回复</Button>
              <Button v-if="item.author.user_id === auth.user?.id && !item.content.startsWith('该回复已由作者删除')" size="sm" variant="ghost" @click="beginCommentEdit(item)">编辑</Button>
              <Button v-if="item.author.user_id === auth.user?.id && !item.content.startsWith('该回复已由作者删除')" size="sm" variant="destructive" :disabled="submitting" @click="removeComment(item)">{{ commentDeleteArmed === item.id ? "再次确认删除" : "删除" }}</Button>
              <Button
                size="sm"
                :variant="item.viewer_has_liked ? 'secondary' : 'ghost'"
                :disabled="commentLikeBusyIds.has(item.id)"
                @click="toggleCommentLike(item)"
              >
                {{ item.viewer_has_liked ? "已赞" : "点赞" }} {{ item.like_count }}
              </Button>
              <Button v-if="auth.isAuthenticated && auth.user?.email_verified" size="sm" variant="ghost" @click="beginReport('comment', item.id)">举报回复</Button>
            </div>
          </article>
          <Button v-if="nextCursor" variant="outline" class="w-full" :disabled="commentsLoading" @click="loadMore">{{ commentsLoading ? "加载中…" : "加载更多回复" }}</Button>
          <div v-if="reportTarget" class="space-y-4 rounded-lg border bg-muted/30 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 class="font-medium">举报{{ reportTarget.type === "post" ? "主题" : "回复" }}</h3>
                <p class="text-sm text-muted-foreground">请说明具体风险，不要在举报中重复粘贴敏感数据。</p>
              </div>
              <Button size="sm" variant="ghost" @click="reportTarget = null">取消</Button>
            </div>
            <div class="space-y-2">
              <Label for="community-post-report-reason">举报原因</Label>
              <Select v-model="reportReason">
                <SelectTrigger id="community-post-report-reason"><SelectValue :placeholder="reportReasonLabel(reportReason)" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="spam">垃圾广告</SelectItem>
                  <SelectItem value="harassment">骚扰攻击</SelectItem>
                  <SelectItem value="privacy">隐私泄露</SelectItem>
                  <SelectItem value="unsafe">不安全内容</SelectItem>
                  <SelectItem value="other">其他问题</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-2">
              <Label for="community-post-report-details">问题说明</Label>
              <Textarea id="community-post-report-details" v-model="reportDetails" :maxlength="1000" placeholder="请用至少 10 个字说明需要复核的原因…" />
            </div>
            <Button :disabled="submitting || reportDetails.trim().length < 10" @click="submitReport">{{ submitting ? "提交中…" : "提交举报" }}</Button>
          </div>
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
