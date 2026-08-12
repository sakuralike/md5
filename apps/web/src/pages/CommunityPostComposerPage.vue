<script setup lang="ts">
import type { CommunityBoard, CommunityBoardCode } from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { createCommunityIdempotencyKey, createCommunityPost, listCommunityBoards } from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const boards = ref<CommunityBoard[]>([]);
const boardCode = ref<CommunityBoardCode>("general");
const title = ref("");
const content = ref("");
const rulesAccepted = ref(false);
const loading = ref(true);
const submitting = ref(false);
const error = ref("");

const canSubmit = computed(
  () => auth.isAuthenticated && auth.user?.email_verified && rulesAccepted.value && title.value.trim().length >= 4 && content.value.trim().length >= 20,
);

onMounted(async () => {
  try {
    boards.value = (await listCommunityBoards()).items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区板块加载失败";
  } finally {
    loading.value = false;
  }
});

async function submit(): Promise<void> {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = "";
  try {
    const created = await createCommunityPost(
      {
        board_code: boardCode.value,
        title: title.value.trim(),
        content: content.value.trim(),
        rules_accepted: true,
      },
      auth.accessToken,
      createCommunityIdempotencyKey("post"),
    );
    await router.push(`/community/posts/${created.id}`);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题发布失败";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <section class="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
    <Card>
      <CardHeader>
        <div class="flex flex-wrap items-center gap-2">
          <Badge>社区</Badge>
          <Badge variant="outline">发布页</Badge>
        </div>
        <CardTitle class="text-2xl">发布新主题</CardTitle>
        <CardDescription>请分享合法授权场景下的经验，不要发布真实密码、令牌、密钥或个人信息。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-5">
        <Alert v-if="error" variant="destructive">
          <AlertTitle>发布失败</AlertTitle>
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>
        <Alert v-if="!auth.isAuthenticated" class="border-primary/30">
          <AlertTitle>需要登录</AlertTitle>
          <AlertDescription>登录并完成邮箱验证后才能发布主题。</AlertDescription>
        </Alert>
        <Alert v-else-if="!auth.user?.email_verified" class="border-primary/30">
          <AlertTitle>需要完成邮箱验证</AlertTitle>
          <AlertDescription>完成邮箱验证后即可参与社区讨论。</AlertDescription>
        </Alert>
        <div class="space-y-2">
          <Label for="community-composer-board">发布到板块</Label>
          <Select v-model="boardCode" :disabled="loading">
            <SelectTrigger id="community-composer-board"><SelectValue placeholder="选择板块" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="board in boards" :key="board.code" :value="board.code">{{ board.name }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label for="community-composer-title">主题标题</Label>
          <Input id="community-composer-title" v-model="title" :maxlength="120" placeholder="例如：合成数据验证失败的排查记录" />
        </div>
        <div class="space-y-2">
          <Label for="community-composer-content">主题内容</Label>
          <Textarea id="community-composer-content" v-model="content" :maxlength="10000" class="min-h-56" placeholder="请描述背景、授权范围、复现步骤和结果…" />
          <p class="text-xs text-muted-foreground">{{ content.length }}/10000，至少 20 个字符。</p>
        </div>
        <div class="flex items-start gap-3">
          <Checkbox id="community-composer-rules" v-model="rulesAccepted" />
          <Label for="community-composer-rules" class="text-sm font-normal leading-5">我确认内容来自合法授权场景，不包含真实密码、令牌、密钥或个人信息。</Label>
        </div>
        <div class="flex flex-wrap gap-3">
          <Button :disabled="submitting || !canSubmit" @click="submit">{{ submitting ? "发布中…" : "发布主题" }}</Button>
          <Button variant="outline" as-child><RouterLink to="/community">返回社区首页</RouterLink></Button>
        </div>
      </CardContent>
    </Card>
  </section>
</template>
