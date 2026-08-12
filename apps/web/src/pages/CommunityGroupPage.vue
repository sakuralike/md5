<script setup lang="ts">
import type { CommunityGroupDetail, CommunityGroupMember, CommunityPostSummary } from "@password-detective/api-contract";
import { computed, onMounted, onServerPrefetch, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { createCommunityIdempotencyKey, decideCommunityGroupMember, getCommunityGroup, listCommunityPosts, setCommunityGroupMembership } from "../services/community";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const auth = useAuthStore();
const slug = computed(() => String(route.params.slug ?? ""));
const group = ref<CommunityGroupDetail | null>(null);
const posts = ref<CommunityPostSummary[]>([]);
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const success = ref("");
const isGovernor = computed(() => group.value?.viewer_role === "owner" || group.value?.viewer_role === "moderator");
const activeMembers = computed(() => group.value?.members.filter((item) => item.status === "active") ?? []);
const pendingMembers = computed(() => group.value?.members.filter((item) => item.status === "pending") ?? []);

onServerPrefetch(loadGroup);
onMounted(() => {
  if (!group.value && !error.value) void loadGroup();
});

async function loadGroup(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const token = auth.isAuthenticated ? auth.accessToken : undefined;
    group.value = await getCommunityGroup(slug.value, token);
    posts.value = (await listCommunityPosts(undefined, token, slug.value)).items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "群组加载失败或无权访问";
  } finally {
    loading.value = false;
  }
}

async function setMembership(joined: boolean): Promise<void> {
  if (!auth.isAuthenticated) return;
  busy.value = true;
  error.value = "";
  try {
    const response = await setCommunityGroupMembership(slug.value, joined, auth.accessToken, createCommunityIdempotencyKey(joined ? "group-join" : "group-leave"));
    success.value = response.message;
    await loadGroup();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "成员状态更新失败";
  } finally {
    busy.value = false;
  }
}

async function decide(member: CommunityGroupMember, decision: "approve" | "reject" | "remove"): Promise<void> {
  busy.value = true;
  error.value = "";
  try {
    const response = await decideCommunityGroupMember(slug.value, member.username, { decision }, auth.accessToken, createCommunityIdempotencyKey("group-member-decision"));
    success.value = response.message;
    await loadGroup();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "成员治理操作失败";
  } finally {
    busy.value = false;
  }
}

function visibilityLabel(value: string): string {
  return value === "private" ? "私密邀请" : value === "approval" ? "申请审批" : "公开加入";
}
function formatDate(value: string): string { return new Date(value).toLocaleString(); }
</script>

<template>
  <section class="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
    <Alert v-if="error" variant="destructive"><AlertTitle>无法访问群组</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
    <Alert v-if="success"><AlertTitle>操作完成</AlertTitle><AlertDescription>{{ success }}</AlertDescription></Alert>
    <div v-if="loading" class="h-64 animate-pulse rounded-2xl bg-muted" />
    <template v-else-if="group">
      <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div class="space-y-3">
            <div class="flex flex-wrap gap-2"><Badge>社区群组</Badge><Badge variant="outline">{{ visibilityLabel(group.visibility) }}</Badge><Badge v-if="group.viewer_role" variant="secondary">{{ group.viewer_role === "owner" ? "群主" : group.viewer_role === "moderator" ? "版主" : "成员" }}</Badge></div>
            <h1 class="text-3xl font-semibold tracking-tight">{{ group.name }}</h1>
            <p class="max-w-3xl text-muted-foreground">{{ group.description || "暂无群组说明" }}</p>
            <p class="text-sm text-muted-foreground">群主 {{ group.owner_username }} · {{ group.member_count }} 名成员 · {{ group.post_count }} 个主题</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button v-if="group.viewer_membership_status === 'active'" as-child><RouterLink :to="{ path: '/community/new', query: { group: group.slug } }">在群组发布</RouterLink></Button>
            <Button v-else-if="auth.isAuthenticated && group.visibility !== 'private'" :disabled="busy || group.viewer_membership_status === 'pending'" @click="setMembership(true)">{{ group.viewer_membership_status === "pending" ? "申请待审批" : "加入群组" }}</Button>
            <Button v-if="group.viewer_membership_status === 'active' && group.viewer_role !== 'owner'" variant="outline" :disabled="busy" @click="setMembership(false)">退出群组</Button>
            <Button variant="outline" as-child><RouterLink to="/community/groups">群组目录</RouterLink></Button>
          </div>
        </div>
      </header>

      <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <CardHeader><CardTitle>群组主题</CardTitle><CardDescription>私密群组主题仅对当前有效成员返回，列表、详情与通知使用同一权限边界。</CardDescription></CardHeader>
          <CardContent class="space-y-3">
            <RouterLink v-for="post in posts" :key="post.id" :to="`/community/posts/${post.id}`" class="block rounded-xl border p-4 transition-colors hover:bg-muted/50">
              <div class="flex flex-wrap items-center gap-2"><Badge variant="outline">{{ post.board_code }}</Badge><h2 class="font-semibold">{{ post.title }}</h2></div>
              <p class="mt-2 line-clamp-2 text-sm text-muted-foreground">{{ post.content_preview }}</p>
              <p class="mt-3 text-xs text-muted-foreground">{{ post.author.username }} · {{ post.reply_count }} 条回复 · {{ formatDate(post.last_activity_at) }}</p>
            </RouterLink>
            <p v-if="posts.length === 0" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">群组内还没有主题。</p>
          </CardContent>
        </Card>

        <div class="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>群组权限说明</CardTitle>
              <CardDescription>加入方式、角色和内容可见范围均由服务端强制执行。</CardDescription>
            </CardHeader>
            <CardContent class="space-y-2 text-sm text-muted-foreground">
              <p v-if="group.visibility === 'public'">公开群组可直接加入；退出后不再拥有群组发帖资格。</p>
              <p v-else-if="group.visibility === 'approval'">申请需群主或群组版主审批；待审批账号不能发布群组主题。</p>
              <p v-else>私密群组不出现在非成员目录中，主题、公开主页动态与通知均只向有效成员开放。</p>
              <p>群主负责成员与版主治理，退出前必须先转让群主身份；全站治理角色不绕过私密内容读取边界。</p>
            </CardContent>
          </Card>
          <Card><CardHeader><CardTitle>成员</CardTitle><CardDescription>群组角色只在本群组内生效。</CardDescription></CardHeader><CardContent class="space-y-2"><div v-for="member in activeMembers" :key="member.username" class="flex items-center justify-between rounded-lg border px-3 py-2"><RouterLink :to="`/community/users/${member.username}`" class="text-sm font-medium hover:underline">{{ member.username }}</RouterLink><Badge variant="outline">{{ member.role === "owner" ? "群主" : member.role === "moderator" ? "版主" : "成员" }}</Badge></div></CardContent></Card>
          <Card v-if="isGovernor && pendingMembers.length"><CardHeader><CardTitle>待审批申请</CardTitle><CardDescription>批准后用户才能发帖；拒绝操作会保留治理记录。</CardDescription></CardHeader><CardContent class="space-y-3"><div v-for="member in pendingMembers" :key="member.username" class="space-y-2 rounded-lg border p-3"><p class="text-sm font-medium">{{ member.username }}</p><div class="flex gap-2"><Button size="sm" :disabled="busy" @click="decide(member, 'approve')">批准</Button><Button size="sm" variant="outline" :disabled="busy" @click="decide(member, 'reject')">拒绝</Button></div></div></CardContent></Card>
        </div>
      </div>
    </template>
  </section>
</template>
