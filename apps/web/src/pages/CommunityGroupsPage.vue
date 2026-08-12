<script setup lang="ts">
import type { CommunityGroupCreateRequest, CommunityGroupSummary, CommunityGroupVisibility } from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { createCommunityGroup, createCommunityIdempotencyKey, listCommunityGroups } from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const groups = ref<CommunityGroupSummary[]>([]);
const slug = ref("");
const name = ref("");
const description = ref("");
const visibility = ref<CommunityGroupVisibility>("public");
const loading = ref(true);
const creating = ref(false);
const error = ref("");
const canCreate = computed(() => auth.isAuthenticated && slug.value.length >= 3 && name.value.trim().length >= 2);

onMounted(() => void loadGroups());

async function loadGroups(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    groups.value = (await listCommunityGroups(auth.isAuthenticated ? auth.accessToken : undefined)).items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "群组目录加载失败";
  } finally {
    loading.value = false;
  }
}

async function createGroup(): Promise<void> {
  if (!canCreate.value) return;
  creating.value = true;
  error.value = "";
  try {
    const payload: CommunityGroupCreateRequest = {
      slug: slug.value.trim(),
      name: name.value.trim(),
      description: description.value.trim(),
      visibility: visibility.value,
    };
    const group = await createCommunityGroup(payload, auth.accessToken, createCommunityIdempotencyKey("group-create"));
    await router.push(`/community/groups/${group.slug}`);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "群组创建失败";
  } finally {
    creating.value = false;
  }
}

function visibilityLabel(value: CommunityGroupVisibility): string {
  return value === "private" ? "私密邀请" : value === "approval" ? "申请审批" : "公开加入";
}
</script>

<template>
  <section class="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
    <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div class="space-y-3">
          <div class="flex gap-2"><Badge>社区群组</Badge><Badge variant="outline">成员治理</Badge></div>
          <h1 class="text-3xl font-semibold tracking-tight">群组目录</h1>
          <p class="max-w-3xl text-muted-foreground">群组独立于社区板块，用于长期协作。公开群组可直接加入，审批群组需群主或版主批准，私密群组仅接受邀请。</p>
        </div>
        <Button variant="outline" as-child><RouterLink to="/community">返回社区首页</RouterLink></Button>
      </div>
    </header>

    <Alert v-if="error" variant="destructive"><AlertTitle>操作失败</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>

    <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Card>
        <CardHeader><CardTitle>可见群组</CardTitle><CardDescription>私密群组只向当前有效成员显示。</CardDescription></CardHeader>
        <CardContent class="grid gap-4 md:grid-cols-2">
          <div v-if="loading" class="h-28 animate-pulse rounded-xl bg-muted md:col-span-2" />
          <RouterLink v-for="group in groups" v-else :key="group.slug" :to="`/community/groups/${group.slug}`" class="rounded-xl border p-5 transition-colors hover:bg-muted/50">
            <div class="flex items-start justify-between gap-3"><h2 class="font-semibold">{{ group.name }}</h2><Badge variant="outline">{{ visibilityLabel(group.visibility) }}</Badge></div>
            <p class="mt-2 line-clamp-3 text-sm text-muted-foreground">{{ group.description || "暂无说明" }}</p>
            <div class="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground"><span>{{ group.member_count }} 名成员</span><span>·</span><span>{{ group.post_count }} 个主题</span><Badge v-if="group.viewer_membership_status === 'active'" variant="secondary">已加入</Badge><Badge v-else-if="group.viewer_membership_status === 'pending'" variant="outline">待审批</Badge></div>
          </RouterLink>
          <p v-if="!loading && groups.length === 0" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground md:col-span-2">暂时没有可见群组。</p>
        </CardContent>
      </Card>

      <Card class="h-fit">
        <CardHeader><CardTitle>创建群组</CardTitle><CardDescription>创建者自动成为群主。群主退出前必须先转让身份。</CardDescription></CardHeader>
        <CardContent class="space-y-4">
          <Alert v-if="!auth.isAuthenticated"><AlertTitle>需要登录</AlertTitle><AlertDescription>登录并验证邮箱后才能创建群组。</AlertDescription></Alert>
          <div class="space-y-2"><Label for="group-slug">群组代码</Label><Input id="group-slug" v-model="slug" placeholder="synthetic-research" /><p class="text-xs text-muted-foreground">仅小写字母、数字和连字符，创建后不可修改。</p></div>
          <div class="space-y-2"><Label for="group-name">群组名称</Label><Input id="group-name" v-model="name" maxlength="64" /></div>
          <div class="space-y-2"><Label for="group-description">群组说明</Label><Textarea id="group-description" v-model="description" maxlength="500" class="min-h-24" /></div>
          <div class="space-y-2"><Label for="group-visibility">加入方式</Label><Select v-model="visibility"><SelectTrigger id="group-visibility"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="public">公开加入</SelectItem><SelectItem value="approval">申请审批</SelectItem><SelectItem value="private">私密邀请</SelectItem></SelectContent></Select></div>
          <Button class="w-full" :disabled="creating || !canCreate" @click="createGroup">{{ creating ? "创建中…" : "创建群组" }}</Button>
        </CardContent>
      </Card>
    </div>
  </section>
</template>
