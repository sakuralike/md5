<script setup lang="ts">
import type {
  CommunityBoard,
  CommunityBoardCode,
  CommunityGroupSummary,
  CommunityImageUploadConfig,
  CommunityPostImage,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createCommunityIdempotencyKey,
  createCommunityPost,
  getCommunityImageUploadConfig,
  listCommunityBoards,
  listCommunityGroups,
  uploadCommunityPostImage,
} from "../services/community";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const boards = ref<CommunityBoard[]>([]);
const boardCode = ref<CommunityBoardCode>(typeof route.query.board === "string" ? route.query.board : "general");
const PUBLIC_GROUP_VALUE = "__public__";
const groupSlug = ref<string>(typeof route.query.group === "string" ? route.query.group : PUBLIC_GROUP_VALUE);
const groups = ref<CommunityGroupSummary[]>([]);
const title = ref("");
const content = ref("");
const rulesAccepted = ref(false);
const loading = ref(true);
const submitting = ref(false);
const error = ref("");
const imageConfig = ref<CommunityImageUploadConfig>({
  enabled: false,
  max_bytes: 5_242_880,
  max_pixels: 20_000_000,
  max_per_post: 4,
});
const attachments = ref<CommunityPostImage[]>([]);
const uploadingImage = ref(false);

const canSubmit = computed(
  () => auth.isAuthenticated && auth.user?.email_verified && rulesAccepted.value && title.value.trim().length >= 4 && content.value.trim().length >= 20,
);

onMounted(async () => {
  try {
    boards.value = (await listCommunityBoards()).items;
    groups.value = (await listCommunityGroups(auth.accessToken)).items;
    imageConfig.value = await getCommunityImageUploadConfig();
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
        group_slug: groupSlug.value === PUBLIC_GROUP_VALUE ? null : groupSlug.value,
        title: title.value.trim(),
        content: content.value.trim(),
        rules_accepted: true,
        attachment_ids: attachments.value.map((item) => item.id),
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

async function uploadImage(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !imageConfig.value.enabled) return;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    error.value = "主题图片仅支持 PNG、JPEG 或 WebP。";
    return;
  }
  if (file.size > imageConfig.value.max_bytes) {
    error.value = `图片不能超过 ${Math.floor(imageConfig.value.max_bytes / 1024 / 1024)} MiB。`;
    return;
  }
  if (attachments.value.length >= imageConfig.value.max_per_post) {
    error.value = `每个主题最多上传 ${imageConfig.value.max_per_post} 张图片。`;
    return;
  }
  uploadingImage.value = true;
  error.value = "";
  try {
    attachments.value = [
      ...attachments.value,
      await uploadCommunityPostImage(file, auth.accessToken),
    ];
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题图片上传失败";
  } finally {
    uploadingImage.value = false;
  }
}

function removeImage(imageId: string): void {
  attachments.value = attachments.value.filter((item) => item.id !== imageId);
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
          <Label for="community-composer-group">发布到群组（可选）</Label>
          <Select v-model="groupSlug" :disabled="loading">
            <SelectTrigger id="community-composer-group"><SelectValue placeholder="公开社区主题" /></SelectTrigger>
            <SelectContent>
              <SelectItem :value="PUBLIC_GROUP_VALUE">公开社区主题</SelectItem>
              <SelectItem v-for="group in groups.filter((item) => item.viewer_membership_status === 'active')" :key="group.slug" :value="group.slug">{{ group.name }}</SelectItem>
            </SelectContent>
          </Select>
          <p class="text-xs text-muted-foreground">私密群组只允许已加入成员发布，群组权限会在服务端再次校验。</p>
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
        <div v-if="imageConfig.enabled" class="space-y-3">
          <div class="flex items-center justify-between gap-3">
            <Label for="community-composer-image">主题图片（可选）</Label>
            <span class="text-xs text-muted-foreground">{{ attachments.length }}/{{ imageConfig.max_per_post }}</span>
          </div>
          <Input
            id="community-composer-image"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :disabled="uploadingImage || attachments.length >= imageConfig.max_per_post"
            @change="uploadImage"
          />
          <div v-if="attachments.length" class="grid gap-2 sm:grid-cols-2">
            <div v-for="image in attachments" :key="image.id" class="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
              <span class="truncate">{{ image.content_type }} · {{ Math.ceil(image.size_bytes / 1024) }} KiB</span>
              <Button type="button" size="sm" variant="ghost" @click="removeImage(image.id)">移除</Button>
            </div>
          </div>
          <p class="text-xs text-muted-foreground">上传后先进入当前账号的待发布附件区，只能绑定到本人新建的公开主题。</p>
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
