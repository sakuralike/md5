<script setup lang="ts">
import type { CommunityPublicProfileResponse } from "@password-detective/api-contract";
import { computed, onMounted, onServerPrefetch, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createCommunityDirectConversation,
  createCommunityIdempotencyKey,
  getCommunityPublicProfile,
  setCommunityUserRelation,
} from "../services/community";
import { resolveCommunityAvatarUrl } from "@/lib/communityAvatar";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const profile = ref<CommunityPublicProfileResponse | null>(null);
const loading = ref(false);
const mutating = ref(false);
const startingConversation = ref(false);
const error = ref("");
const success = ref("");

const username = computed(() => String(route.params.username ?? ""));
const avatarInitial = computed(() => profile.value?.display_name.trim().slice(0, 1).toUpperCase() || "社");
const avatarSrc = computed(() => (profile.value ? resolveCommunityAvatarUrl(profile.value) : null));
const contentHidden = computed(() => {
  const relation = profile.value?.relationship;
  return Boolean(relation?.viewer_is_blocking || relation?.viewer_is_blocked || relation?.viewer_is_muting);
});

async function load(): Promise<void> {
  if (!username.value) return;
  loading.value = true;
  error.value = "";
  try {
    profile.value = await getCommunityPublicProfile(
      username.value,
      auth.isAuthenticated ? auth.accessToken : undefined,
    );
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载社区公开主页";
  } finally {
    loading.value = false;
  }
}

async function startDirectMessage(): Promise<void> {
  if (!auth.isAuthenticated || !profile.value || startingConversation.value) return;
  startingConversation.value = true;
  error.value = "";
  success.value = "";
  try {
    const response = await createCommunityDirectConversation(
      { recipient_username: profile.value.username },
      auth.accessToken,
      createCommunityIdempotencyKey("direct-conversation"),
    );
    await router.push(`/community/messages/${response.conversation.id}`);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法发起私信会话";
  } finally {
    startingConversation.value = false;
  }
}

async function changeRelation(
  relation: "follow" | "block" | "mute",
  enabled: boolean,
): Promise<void> {
  if (!auth.isAuthenticated || !profile.value || mutating.value) return;
  mutating.value = true;
  error.value = "";
  success.value = "";
  try {
    const result = await setCommunityUserRelation(
      profile.value.username,
      relation,
      enabled,
      auth.accessToken,
      createCommunityIdempotencyKey(
        enabled
          ? relation
          : ({ follow: "unfollow", block: "unblock", mute: "unmute" } as const)[relation],
      ),
    );
    profile.value = {
      ...profile.value,
      relationship: result.relationship,
    };
    success.value = result.message;
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区关系更新失败";
  } finally {
    mutating.value = false;
  }
}

watch(username, () => load());
onMounted(() => load());
onServerPrefetch(() => load());
</script>

<template>
  <section class="mx-auto max-w-6xl space-y-6">
    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>公开主页暂时不可用</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Alert v-if="success">
      <AlertTitle>关系已更新</AlertTitle>
      <AlertDescription>{{ success }}</AlertDescription>
    </Alert>

    <div v-if="loading" class="space-y-4">
      <div class="h-52 animate-pulse rounded-2xl bg-muted" />
      <div class="h-40 animate-pulse rounded-2xl bg-muted" />
    </div>

    <template v-else-if="profile">
      <Card>
        <CardContent class="flex flex-col gap-6 p-6 sm:flex-row sm:items-start sm:p-8">
          <Avatar class="h-20 w-20 shrink-0 border-2 border-background shadow-md">
            <AvatarImage v-if="avatarSrc" :src="avatarSrc" :alt="`${profile.display_name} 的头像`" />
            <AvatarFallback class="bg-primary text-3xl font-semibold text-primary-foreground">{{ avatarInitial }}</AvatarFallback>
          </Avatar>
          <div class="min-w-0 flex-1 space-y-4">
            <div class="space-y-2">
              <div class="flex flex-wrap items-center gap-2">
                <h1 class="text-2xl font-semibold tracking-tight">{{ profile.display_name }}</h1>
                <Badge variant="secondary">{{ profile.role }}</Badge>
                <Badge variant="outline">{{ profile.level.name }}</Badge>
              </div>
              <p class="text-sm text-muted-foreground">@{{ profile.username }} · 加入于 {{ profile.registered_month }}</p>
              <p v-if="profile.bio" class="max-w-3xl text-sm leading-6 text-foreground">{{ profile.bio }}</p>
              <p v-else class="text-sm text-muted-foreground">该用户尚未填写公开社区简介。</p>
            </div>
            <div class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <RouterLink :to="`/community/users/${profile.username}/followers`" class="rounded-lg border p-3 hover:bg-muted/50">
                <span class="block font-semibold">{{ profile.stats.follower_count }}</span>
                <span class="text-muted-foreground">关注者</span>
              </RouterLink>
              <RouterLink :to="`/community/users/${profile.username}/following`" class="rounded-lg border p-3 hover:bg-muted/50">
                <span class="block font-semibold">{{ profile.stats.following_count }}</span>
                <span class="text-muted-foreground">正在关注</span>
              </RouterLink>
              <div class="rounded-lg border p-3"><span class="block font-semibold">{{ profile.stats.post_count }}</span><span class="text-muted-foreground">公开主题</span></div>
              <div class="rounded-lg border p-3"><span class="block font-semibold">{{ profile.stats.comment_count }}</span><span class="text-muted-foreground">公开回复</span></div>
            </div>
          </div>
          <div v-if="auth.isAuthenticated && !profile.relationship.viewer_is_self" class="flex flex-wrap gap-2">
            <Button
              v-if="!profile.relationship.viewer_is_blocking && !profile.relationship.viewer_is_blocked"
              variant="secondary"
              :disabled="startingConversation"
              @click="startDirectMessage"
            >
              {{ startingConversation ? "正在打开…" : "发送私信" }}
            </Button>
            <Button
              :disabled="mutating || profile.relationship.viewer_is_blocking || profile.relationship.viewer_is_blocked"
              @click="changeRelation('follow', !profile.relationship.viewer_is_following)"
            >
              {{ profile.relationship.viewer_is_following ? "取消关注" : "关注" }}
            </Button>
            <Button variant="outline" :disabled="mutating" @click="changeRelation('mute', !profile.relationship.viewer_is_muting)">
              {{ profile.relationship.viewer_is_muting ? "取消静音" : "静音" }}
            </Button>
            <Button variant="destructive" :disabled="mutating" @click="changeRelation('block', !profile.relationship.viewer_is_blocking)">
              {{ profile.relationship.viewer_is_blocking ? "解除拉黑" : "拉黑" }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Alert v-if="contentHidden">
        <AlertTitle>已按你的关系设置过滤动态</AlertTitle>
        <AlertDescription>拉黑或静音不会影响对方账号状态；当前仅隐藏其公开主题和回复。</AlertDescription>
      </Alert>

      <div v-else class="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>最近公开主题</CardTitle>
            <CardDescription>仅展示仍可公开访问的主题。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-3">
            <RouterLink v-for="post in profile.recent_posts" :key="post.id" :to="`/community/posts/${post.id}`" class="block rounded-lg border p-4 hover:bg-muted/50">
              <div class="space-y-2"><h2 class="font-medium">{{ post.title }}</h2><p class="line-clamp-2 text-sm text-muted-foreground">{{ post.content_preview }}</p><p class="text-xs text-muted-foreground">{{ post.reply_count }} 条回复 · {{ post.like_count }} 赞</p></div>
            </RouterLink>
            <p v-if="profile.recent_posts.length === 0" class="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">尚无公开主题。</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>最近公开回复</CardTitle>
            <CardDescription>不会显示私密群组、已移除内容或访问日志。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-3">
            <RouterLink v-for="comment in profile.recent_comments" :key="comment.id" :to="`/community/posts/${comment.post_id}`" class="block rounded-lg border p-4 hover:bg-muted/50">
              <div class="space-y-2"><p class="font-medium">{{ comment.post_title }}</p><p class="line-clamp-2 text-sm text-muted-foreground">{{ comment.content_preview }}</p><p class="text-xs text-muted-foreground">{{ comment.like_count }} 赞</p></div>
            </RouterLink>
            <p v-if="profile.recent_comments.length === 0" class="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">尚无公开回复。</p>
          </CardContent>
        </Card>
      </div>
    </template>
  </section>
</template>
