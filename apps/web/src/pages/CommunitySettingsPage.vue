<script setup lang="ts">
import type {
  CommunityInteractionPolicy,
  CommunityOwnProfileResponse,
  CommunityRelationVisibility,
} from "@password-detective/api-contract";
import { onMounted, onServerPrefetch, ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createCommunityIdempotencyKey,
  getCommunityOwnProfile,
  updateCommunityOwnProfile,
  updateCommunityPrivacy,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const profile = ref<CommunityOwnProfileResponse | null>(null);
const displayName = ref("");
const bio = ref("");
const followerVisibility = ref<CommunityRelationVisibility>("public");
const followingVisibility = ref<CommunityRelationVisibility>("public");
const messagePolicy = ref<CommunityInteractionPolicy>("following");
const mentionPolicy = ref<CommunityInteractionPolicy>("everyone");
const loading = ref(false);
const savingProfile = ref(false);
const savingPrivacy = ref(false);
const error = ref("");
const success = ref("");

function applyProfile(next: CommunityOwnProfileResponse): void {
  profile.value = next;
  displayName.value = next.display_name;
  bio.value = next.bio;
  followerVisibility.value = next.follower_visibility;
  followingVisibility.value = next.following_visibility;
  messagePolicy.value = next.message_policy;
  mentionPolicy.value = next.mention_policy;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    applyProfile(await getCommunityOwnProfile(auth.accessToken));
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载社区资料";
  } finally {
    loading.value = false;
  }
}

async function saveProfile(regenerateAvatar = false): Promise<void> {
  if (!displayName.value.trim()) return;
  savingProfile.value = true;
  error.value = "";
  success.value = "";
  try {
    const next = await updateCommunityOwnProfile(
      {
        display_name: displayName.value.trim(),
        bio: bio.value.trim(),
        regenerate_avatar: regenerateAvatar,
      },
      auth.accessToken,
      createCommunityIdempotencyKey("profile-update"),
    );
    applyProfile(next);
    success.value = regenerateAvatar ? "公开资料与合成头像已更新" : "公开资料已更新";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区资料保存失败";
  } finally {
    savingProfile.value = false;
  }
}

async function savePrivacy(): Promise<void> {
  savingPrivacy.value = true;
  error.value = "";
  success.value = "";
  try {
    const next = await updateCommunityPrivacy(
      {
        follower_visibility: followerVisibility.value,
        following_visibility: followingVisibility.value,
        message_policy: messagePolicy.value,
        mention_policy: mentionPolicy.value,
      },
      auth.accessToken,
      createCommunityIdempotencyKey("privacy-update"),
    );
    applyProfile(next);
    success.value = "社区隐私与互动策略已更新";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区隐私保存失败";
  } finally {
    savingPrivacy.value = false;
  }
}

onMounted(() => load());
onServerPrefetch(() => load());
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-6">
    <header class="space-y-2">
      <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Community identity</p>
      <h1 class="text-3xl font-semibold tracking-tight">社区资料与隐私</h1>
      <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
        用户名是注册后不可变的内容归属标识；这里维护可编辑展示名、公开简介、合成头像和互动边界。
      </p>
    </header>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>操作未完成</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Alert v-if="success">
      <AlertTitle>设置已保存</AlertTitle>
      <AlertDescription>{{ success }}</AlertDescription>
    </Alert>

    <div v-if="loading" class="h-56 animate-pulse rounded-2xl bg-muted" />
    <div v-else-if="profile" class="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>公开身份</CardTitle>
          <CardDescription>不会公开邮箱、精确注册时间、登录活动、设备或积分流水。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-5">
          <div class="space-y-2">
            <Label for="community-username">用户名</Label>
            <Input id="community-username" :model-value="profile.username" disabled />
            <p class="text-xs text-muted-foreground">注册后不可修改。</p>
          </div>
          <div class="space-y-2">
            <Label for="community-display-name">公开展示名</Label>
            <Input id="community-display-name" v-model="displayName" maxlength="48" />
          </div>
          <div class="space-y-2">
            <Label for="community-bio">公开简介</Label>
            <Textarea id="community-bio" v-model="bio" maxlength="300" rows="6" />
            <p class="text-xs text-muted-foreground">{{ bio.length }}/300；请勿填写密码、令牌或个人敏感信息。</p>
          </div>
        </CardContent>
        <CardFooter class="flex flex-wrap gap-2">
          <Button :disabled="savingProfile || !displayName.trim()" @click="saveProfile(false)">
            {{ savingProfile ? "保存中…" : "保存公开资料" }}
          </Button>
          <Button variant="outline" :disabled="savingProfile" @click="saveProfile(true)">更换合成头像</Button>
          <Button as-child variant="ghost">
            <RouterLink :to="`/community/users/${profile.username}`">查看公开主页</RouterLink>
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>关系与互动边界</CardTitle>
          <CardDescription>拉黑会移除双方关注并阻断关注、私信与提及；静音只影响你的视图。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-5">
          <div class="space-y-2">
            <Label>谁能查看关注者列表</Label>
            <Select v-model="followerVisibility">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="public">所有人</SelectItem><SelectItem value="private">仅自己</SelectItem></SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>谁能查看正在关注列表</Label>
            <Select v-model="followingVisibility">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="public">所有人</SelectItem><SelectItem value="private">仅自己</SelectItem></SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>谁可以发起私信</Label>
            <Select v-model="messagePolicy">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="everyone">所有登录用户</SelectItem><SelectItem value="following">仅我关注的人</SelectItem><SelectItem value="nobody">任何人都不可以</SelectItem></SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>谁可以提及我</Label>
            <Select v-model="mentionPolicy">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="everyone">所有登录用户</SelectItem><SelectItem value="following">仅我关注的人</SelectItem><SelectItem value="nobody">任何人都不可以</SelectItem></SelectContent>
            </Select>
          </div>
        </CardContent>
        <CardFooter>
          <Button :disabled="savingPrivacy" @click="savePrivacy">
            {{ savingPrivacy ? "保存中…" : "保存隐私设置" }}
          </Button>
        </CardFooter>
      </Card>
    </div>
  </section>
</template>
