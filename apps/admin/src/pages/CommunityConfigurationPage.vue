<script setup lang="ts">
import type {
  AdminCommunityBoardCreateRequest,
  AdminCommunityBoardResponse,
  AdminCommunityBoardUpdateRequest,
  CommunityBoardStatus,
  UserRole,
  CommunityImageUploadConfig,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  createCommunityBoard,
  createCommunityConfigurationKey,
  listCommunityBoards,
  updateCommunityBoard,
  getCommunityImageUploadConfig,
  saveCommunityImageUploadConfig,
} from "../services/communityConfiguration";
import { useAdminAuthStore } from "../stores/auth";

interface BoardDraft {
  name: string;
  description: string;
  sort_order: number;
  minimum_role: UserRole;
  is_read_only: boolean;
  status: CommunityBoardStatus;
}

const auth = useAdminAuthStore();
const boards = ref<AdminCommunityBoardResponse[]>([]);
const selectedCode = ref("");
const draft = ref<BoardDraft>(emptyDraft());
const createCode = ref("");
const createDraft = ref<BoardDraft>(emptyDraft());
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const success = ref("");
const imageConfig = ref<CommunityImageUploadConfig>({ enabled: false, max_bytes: 5_242_880, max_pixels: 20_000_000, max_per_post: 4 });
const imageConfigBusy = ref(false);

const selectedBoard = computed(() =>
  boards.value.find((board) => board.code === selectedCode.value) ?? null,
);
const canCreate = computed(() =>
  /^[a-z0-9][a-z0-9_]{2,31}$/.test(createCode.value.trim())
  && createDraft.value.name.trim().length >= 2,
);
const canUpdate = computed(() => selectedBoard.value !== null && draft.value.name.trim().length >= 2);

onMounted(() => {
  void loadBoards();
  void loadImageConfig();
});

async function loadImageConfig(): Promise<void> {
  try {
    imageConfig.value = (await getCommunityImageUploadConfig(auth.accessToken)).config;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "图片上传配置加载失败";
  }
}

async function saveImageConfig(): Promise<void> {
  imageConfigBusy.value = true;
  error.value = "";
  success.value = "";
  try {
    imageConfig.value = (await saveCommunityImageUploadConfig(imageConfig.value, auth.accessToken)).config;
    success.value = imageConfig.value.enabled ? "论坛图片上传已启用并写入审计日志。" : "论坛图片上传已关闭并写入审计日志。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "图片上传配置保存失败";
  } finally {
    imageConfigBusy.value = false;
  }
}

function emptyDraft(): BoardDraft {
  return {
    name: "",
    description: "",
    sort_order: 0,
    minimum_role: "user",
    is_read_only: false,
    status: "active",
  };
}

function selectBoard(board: AdminCommunityBoardResponse): void {
  selectedCode.value = board.code;
  draft.value = {
    name: board.name,
    description: board.description,
    sort_order: board.sort_order,
    minimum_role: board.minimum_role,
    is_read_only: board.is_read_only,
    status: board.status,
  };
  success.value = "";
  error.value = "";
}

async function loadBoards(preferredCode?: string): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    boards.value = (await listCommunityBoards(auth.accessToken)).items;
    const next = boards.value.find((board) => board.code === preferredCode) ?? boards.value[0];
    if (next) selectBoard(next);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区板块配置加载失败";
  } finally {
    loading.value = false;
  }
}

async function submitCreate(): Promise<void> {
  if (!canCreate.value) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const payload: AdminCommunityBoardCreateRequest = {
      code: createCode.value.trim(),
      ...normalizedDraft(createDraft.value),
    };
    const response = await createCommunityBoard(
      payload,
      auth.accessToken,
      createCommunityConfigurationKey("create"),
    );
    createCode.value = "";
    createDraft.value = emptyDraft();
    success.value = `板块“${response.board.name}”已创建并写入审计日志。`;
    await loadBoards(response.board.code);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区板块创建失败";
  } finally {
    busy.value = false;
  }
}

async function submitUpdate(): Promise<void> {
  if (!selectedBoard.value || !canUpdate.value) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const payload: AdminCommunityBoardUpdateRequest = normalizedDraft(draft.value);
    const response = await updateCommunityBoard(
      selectedBoard.value.code,
      payload,
      auth.accessToken,
      createCommunityConfigurationKey("update"),
    );
    success.value = `板块“${response.board.name}”配置已更新并写入审计日志。`;
    await loadBoards(response.board.code);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区板块更新失败";
  } finally {
    busy.value = false;
  }
}

function normalizedDraft(value: BoardDraft): BoardDraft {
  return {
    ...value,
    name: value.name.trim(),
    description: value.description.trim(),
    sort_order: Number(value.sort_order),
  };
}

function roleLabel(role: UserRole): string {
  const labels: Record<UserRole, string> = {
    user: "普通用户",
    trusted_contributor: "可信贡献者",
    moderator: "全站版主",
    admin: "管理员",
    service: "服务账号",
  };
  return labels[role];
}
</script>

<template>
  <section class="space-y-6">
    <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div class="space-y-3">
          <div class="flex flex-wrap gap-2">
            <Badge>社区配置</Badge>
            <Badge variant="outline">管理员 + TOTP</Badge>
          </div>
          <h1 class="text-3xl font-semibold tracking-tight">社区板块配置工作台</h1>
          <p class="max-w-3xl text-muted-foreground">
            参考成熟论坛的板块目录与权限说明，将板块排序、最低发帖角色、只读状态和逻辑停用集中治理。所有变更均要求管理员 MFA、幂等键和审计记录。
          </p>
        </div>
        <Button type="button" variant="outline" :disabled="loading" @click="loadBoards(selectedCode)">
          {{ loading ? "刷新中…" : "刷新配置" }}
        </Button>
      </div>
    </header>

    <div v-if="error" role="alert" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
      <strong class="font-semibold">操作失败：</strong>{{ error }}
    </div>
    <div v-if="success" role="status" class="rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm">
      {{ success }}
    </div>

    <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="权限效果说明">
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <h2 class="font-semibold">最低发帖角色</h2>
        <p class="mt-2 text-sm text-muted-foreground">未达到角色门槛的账号仍可阅读，但发布主题会被服务端拒绝。</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <h2 class="font-semibold">只读状态</h2>
        <p class="mt-2 text-sm text-muted-foreground">立即阻止所有新主题，历史内容和审计证据保持可追溯。</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <h2 class="font-semibold">逻辑停用</h2>
        <p class="mt-2 text-sm text-muted-foreground">从公开板块目录和发帖选择中移除，不物理删除既有主题。</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <h2 class="font-semibold">排序规则</h2>
        <p class="mt-2 text-sm text-muted-foreground">数字越小越靠前；代码创建后保持稳定，保证历史链接与数据兼容。</p>
      </article>
    </section>

    <section class="space-y-5 rounded-2xl border bg-card p-5 shadow-sm sm:p-6" aria-labelledby="image-upload-heading">
      <div>
        <h2 id="image-upload-heading" class="text-lg font-semibold">论坛图片上传</h2>
        <p class="mt-1 text-sm text-muted-foreground">默认关闭。仅允许 PNG、JPEG、WebP；服务端校验文件签名、元数据、尺寸和像素总量，图片只能作为主题附件引用。</p>
      </div>
      <div class="grid gap-4 md:grid-cols-4 md:items-end">
        <div class="space-y-2">
          <Label>上传状态</Label>
          <Select :model-value="imageConfig.enabled ? 'enabled' : 'disabled'" @update:model-value="imageConfig.enabled = $event === 'enabled'">
            <SelectTrigger aria-label="论坛图片上传状态"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="disabled">关闭</SelectItem><SelectItem value="enabled">开启</SelectItem></SelectContent>
          </Select>
        </div>
        <div class="space-y-2"><Label for="image-max-bytes">单张大小（字节）</Label><Input id="image-max-bytes" v-model.number="imageConfig.max_bytes" type="number" min="1024" max="20971520" /></div>
        <div class="space-y-2"><Label for="image-max-pixels">像素上限</Label><Input id="image-max-pixels" v-model.number="imageConfig.max_pixels" type="number" min="65536" max="100000000" /></div>
        <div class="space-y-2"><Label for="image-max-count">每主题张数</Label><Input id="image-max-count" v-model.number="imageConfig.max_per_post" type="number" min="1" max="6" /></div>
      </div>
      <Button :disabled="imageConfigBusy" @click="saveImageConfig"><span>{{ imageConfigBusy ? "保存中…" : "保存图片配置" }}</span></Button>
    </section>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
      <section class="overflow-hidden rounded-2xl border bg-card shadow-sm">
        <div class="border-b p-5">
          <h2 class="text-lg font-semibold">现有板块</h2>
          <p class="mt-1 text-sm text-muted-foreground">选择板块后在右侧修改；停用和只读均为可恢复配置。</p>
        </div>
        <div v-if="loading" class="h-48 animate-pulse bg-muted/60" />
        <div v-else class="divide-y">
          <Button
            v-for="board in boards"
            :key="board.code"
            type="button"
            variant="ghost"
            class="h-auto w-full justify-start rounded-none px-5 py-4 text-left"
            :class="selectedCode === board.code ? 'bg-accent' : ''"
            @click="selectBoard(board)"
          >
            <span class="min-w-0 flex-1">
              <span class="flex flex-wrap items-center gap-2">
                <strong>{{ board.name }}</strong>
                <Badge variant="outline">{{ board.code }}</Badge>
                <Badge v-if="board.status === 'inactive'" variant="destructive">已停用</Badge>
                <Badge v-if="board.is_read_only" variant="secondary">只读</Badge>
              </span>
              <span class="mt-1 block whitespace-normal text-sm font-normal text-muted-foreground">
                {{ board.description || "暂无说明" }}
              </span>
              <span class="mt-2 block text-xs font-normal text-muted-foreground">
                排序 {{ board.sort_order }} · 最低角色 {{ roleLabel(board.minimum_role) }} · {{ board.post_count }} 个已发布主题
              </span>
            </span>
          </Button>
          <p v-if="boards.length === 0" class="p-8 text-center text-sm text-muted-foreground">暂无板块配置。</p>
        </div>
      </section>

      <section class="h-fit rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
        <div class="mb-5">
          <h2 class="text-lg font-semibold">编辑板块</h2>
          <p class="mt-1 text-sm text-muted-foreground">板块代码不可修改；权限与状态更新会立即生效。</p>
        </div>
        <div v-if="selectedBoard" class="space-y-4">
          <div class="space-y-2">
            <Label for="board-edit-code">板块代码</Label>
            <Input id="board-edit-code" :model-value="selectedBoard.code" disabled />
          </div>
          <div class="space-y-2">
            <Label for="board-edit-name">板块名称</Label>
            <Input id="board-edit-name" v-model="draft.name" :maxlength="48" />
          </div>
          <div class="space-y-2">
            <Label for="board-edit-description">板块说明</Label>
            <Textarea id="board-edit-description" v-model="draft.description" class="min-h-24" :maxlength="300" />
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <Label for="board-edit-sort">排序</Label>
              <Input id="board-edit-sort" v-model.number="draft.sort_order" type="number" min="-10000" max="10000" />
            </div>
            <div class="space-y-2">
              <Label for="board-edit-role">最低发帖角色</Label>
              <Select v-model="draft.minimum_role">
                <SelectTrigger id="board-edit-role"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">普通用户</SelectItem>
                  <SelectItem value="trusted_contributor">可信贡献者</SelectItem>
                  <SelectItem value="moderator">全站版主</SelectItem>
                  <SelectItem value="admin">管理员</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div class="space-y-2">
            <Label for="board-edit-status">板块状态</Label>
            <Select v-model="draft.status">
              <SelectTrigger id="board-edit-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="active">启用</SelectItem>
                <SelectItem value="inactive">逻辑停用</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex items-start gap-3 rounded-xl border p-4">
            <Checkbox id="board-edit-read-only" v-model="draft.is_read_only" />
            <div class="space-y-1">
              <Label for="board-edit-read-only">设为只读</Label>
              <p class="text-xs text-muted-foreground">开启后任何角色都不能在该板块发布新主题。</p>
            </div>
          </div>
          <Button type="button" class="w-full" :disabled="busy || !canUpdate" @click="submitUpdate">
            {{ busy ? "保存中…" : "保存板块配置" }}
          </Button>
        </div>
        <p v-else class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">请选择一个板块。</p>
      </section>
    </div>

    <section class="rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
      <div class="mb-5">
        <h2 class="text-lg font-semibold">新增板块</h2>
        <p class="mt-1 text-sm text-muted-foreground">仅管理员可创建。代码仅允许小写字母、数字和下划线，创建后不可修改。</p>
      </div>
      <div class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <div class="space-y-2">
          <Label for="board-create-code">板块代码</Label>
          <Input id="board-create-code" v-model="createCode" placeholder="synthetic_lab" :maxlength="32" />
        </div>
        <div class="space-y-2">
          <Label for="board-create-name">板块名称</Label>
          <Input id="board-create-name" v-model="createDraft.name" :maxlength="48" />
        </div>
        <div class="space-y-2">
          <Label for="board-create-sort">排序</Label>
          <Input id="board-create-sort" v-model.number="createDraft.sort_order" type="number" min="-10000" max="10000" />
        </div>
        <div class="space-y-2 lg:col-span-2">
          <Label for="board-create-description">板块说明</Label>
          <Textarea id="board-create-description" v-model="createDraft.description" class="min-h-24" :maxlength="300" />
        </div>
        <div class="space-y-2">
          <Label for="board-create-role">最低发帖角色</Label>
          <Select v-model="createDraft.minimum_role">
            <SelectTrigger id="board-create-role"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="user">普通用户</SelectItem>
              <SelectItem value="trusted_contributor">可信贡献者</SelectItem>
              <SelectItem value="moderator">全站版主</SelectItem>
              <SelectItem value="admin">管理员</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div class="mt-4 flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-start gap-3">
          <Checkbox id="board-create-read-only" v-model="createDraft.is_read_only" />
          <div>
            <Label for="board-create-read-only">创建为只读板块</Label>
            <p class="mt-1 text-xs text-muted-foreground">适用于公告、规则或暂不开放发帖的目录。</p>
          </div>
        </div>
        <Button type="button" :disabled="busy || !canCreate" @click="submitCreate">
          {{ busy ? "创建中…" : "创建板块" }}
        </Button>
      </div>
    </section>
  </section>
</template>
