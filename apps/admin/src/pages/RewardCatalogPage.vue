<script setup lang="ts">
import type {
  AdminRewardCatalogItem,
  RewardCatalogCreateRequest,
  RewardCatalogStatus,
  RewardCatalogUpdateRequest,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createAdminRewardCatalog,
  createRewardCatalogKey,
  listAdminRewardCatalog,
  updateAdminRewardCatalog,
} from "../services/rewards";
import { useAdminAuthStore } from "../stores/auth";

interface CatalogDraft {
  slug: string;
  name: string;
  description: string;
  cost_points: number;
  stock: number;
  per_user_limit: number;
  status: RewardCatalogStatus;
  reason_code: string;
}

const auth = useAdminAuthStore();
const items = ref<AdminRewardCatalogItem[]>([]);
const selectedId = ref("");
const statusFilter = ref<RewardCatalogStatus | "">("");
const createDraft = ref<CatalogDraft>(emptyDraft());
const editDraft = ref<CatalogDraft>(emptyDraft());
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const message = ref("");

const selected = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null);
const canCreate = computed(
  () => createDraft.value.slug.trim().length >= 3 && createDraft.value.name.trim().length >= 2,
);
const canUpdate = computed(() => selected.value !== null && editDraft.value.name.trim().length >= 2);

function emptyDraft(): CatalogDraft {
  return {
    slug: "",
    name: "",
    description: "",
    cost_points: 100,
    stock: 100,
    per_user_limit: 1,
    status: "draft",
    reason_code: "catalog_initial_setup",
  };
}

function requireToken(): string {
  if (!auth.accessToken) throw new Error("管理会话已失效，请重新登录");
  return auth.accessToken;
}

function selectItem(item: AdminRewardCatalogItem): void {
  selectedId.value = item.id;
  editDraft.value = {
    slug: item.slug,
    name: item.name,
    description: item.description,
    cost_points: item.cost_points,
    stock: item.stock,
    per_user_limit: item.per_user_limit,
    status: item.status,
    reason_code: "catalog_update",
  };
  error.value = "";
  message.value = "";
}

function statusLabel(value: RewardCatalogStatus): string {
  return { draft: "草稿", active: "上架", inactive: "停用" }[value];
}

function stockLabel(stock: number): string {
  return stock === 0 ? "无库存" : stock <= 10 ? "库存紧张" : "库存充足";
}

function describeError(value: unknown): string {
  return value instanceof Error ? value.message : "商城目录操作失败";
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listAdminRewardCatalog(statusFilter.value, requireToken());
    items.value = response.items;
    if (selectedId.value) {
      const refreshed = items.value.find((item) => item.id === selectedId.value);
      if (refreshed) selectItem(refreshed);
      else selectedId.value = "";
    }
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function createItem(): Promise<void> {
  if (!canCreate.value) return;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    const payload: RewardCatalogCreateRequest = {
      ...createDraft.value,
      kind: "virtual",
      slug: createDraft.value.slug.trim().toLowerCase(),
      name: createDraft.value.name.trim(),
      description: createDraft.value.description.trim(),
      reason_code: createDraft.value.reason_code.trim(),
    };
    const item = await createAdminRewardCatalog(payload, requireToken(), createRewardCatalogKey("create"));
    createDraft.value = emptyDraft();
    message.value = `商品“${item.name}”已创建。`;
    await load();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

async function updateItem(): Promise<void> {
  if (!selected.value || !canUpdate.value) return;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    const payload: RewardCatalogUpdateRequest = {
      name: editDraft.value.name.trim(),
      description: editDraft.value.description.trim(),
      kind: "virtual",
      cost_points: Number(editDraft.value.cost_points),
      stock: Number(editDraft.value.stock),
      per_user_limit: Number(editDraft.value.per_user_limit),
      status: editDraft.value.status,
      expected_version: selected.value.version,
      reason_code: editDraft.value.reason_code.trim(),
    };
    const item = await updateAdminRewardCatalog(selected.value.id, payload, requireToken(), createRewardCatalogKey("update"));
    message.value = `商品“${item.name}”已更新。`;
    await load();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

onMounted(() => void load());
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">P2 · 积分商城</p>
        <h1 class="text-2xl font-semibold tracking-tight">虚拟商品目录</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          管理使用已结算积分兑换的虚拟权益目录。首期只治理商品，不执行下单、扣积分或实物履约。
        </p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load">刷新目录</Button>
    </header>

    <p v-if="error" class="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>
    <p v-if="message" class="rounded-md bg-primary/10 px-4 py-3 text-sm text-primary" role="status">{{ message }}</p>

    <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.8fr)]">
      <Card>
        <CardHeader class="flex flex-row items-center justify-between gap-4">
          <div><CardTitle>商品目录</CardTitle><CardDescription>只有上架且为虚拟权益的商品会出现在用户商城。</CardDescription></div>
          <Select v-model="statusFilter" @update:model-value="load">
            <SelectTrigger aria-label="商品状态筛选" class="w-28"><SelectValue placeholder="全部状态" /></SelectTrigger>
            <SelectContent><SelectItem value="">全部状态</SelectItem><SelectItem value="draft">草稿</SelectItem><SelectItem value="active">上架</SelectItem><SelectItem value="inactive">停用</SelectItem></SelectContent>
          </Select>
        </CardHeader>
        <CardContent class="space-y-3">
          <div v-if="loading" class="h-24 animate-pulse rounded-md bg-muted" />
          <Button v-for="item in items" v-else :key="item.id" type="button" variant="ghost" class="grid h-auto w-full gap-3 rounded-md border p-4 text-left transition-colors hover:bg-muted/50 sm:grid-cols-[minmax(0,1fr)_auto]" :class="item.id === selectedId && 'border-primary bg-primary/5'" @click="selectItem(item)">
            <div class="min-w-0 space-y-1"><div class="flex flex-wrap items-center gap-2"><strong class="truncate">{{ item.name }}</strong><Badge variant="outline">{{ statusLabel(item.status) }}</Badge><Badge variant="secondary">虚拟权益</Badge></div><p class="line-clamp-2 text-sm text-muted-foreground">{{ item.description }}</p><p class="text-xs text-muted-foreground">{{ item.slug }} · 版本 {{ item.version }}</p></div>
            <div class="text-left text-sm sm:text-right"><strong>{{ item.cost_points }} 积分</strong><p class="text-xs text-muted-foreground">{{ stockLabel(item.stock) }} · {{ item.stock }} 件</p><p class="text-xs text-muted-foreground">每人限 {{ item.per_user_limit }} 件</p></div>
          </Button>
          <p v-if="!loading && items.length === 0" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">暂无商品，请从右侧创建虚拟商品。</p>
        </CardContent>
      </Card>

      <div class="space-y-5">
        <Card>
          <CardHeader><CardTitle>创建商品</CardTitle><CardDescription>商品代码创建后不可修改，商品类型首期固定为虚拟权益。</CardDescription></CardHeader>
          <CardContent class="space-y-4">
            <div class="grid gap-2"><Label for="reward-create-slug">商品代码</Label><Input id="reward-create-slug" v-model="createDraft.slug" placeholder="synthetic-reward" /></div>
            <div class="grid gap-2"><Label for="reward-create-name">商品名称</Label><Input id="reward-create-name" v-model="createDraft.name" maxlength="100" /></div>
            <div class="grid gap-2"><Label for="reward-create-description">商品说明</Label><Textarea id="reward-create-description" v-model="createDraft.description" maxlength="2000" class="min-h-24" /></div>
            <div class="grid gap-3 sm:grid-cols-3"><div class="grid gap-2"><Label for="reward-create-cost">积分价格</Label><Input id="reward-create-cost" v-model.number="createDraft.cost_points" type="number" min="1" /></div><div class="grid gap-2"><Label for="reward-create-stock">库存</Label><Input id="reward-create-stock" v-model.number="createDraft.stock" type="number" min="0" /></div><div class="grid gap-2"><Label for="reward-create-limit">每人限购</Label><Input id="reward-create-limit" v-model.number="createDraft.per_user_limit" type="number" min="1" /></div></div>
            <div class="grid gap-2"><Label for="reward-create-status">初始状态</Label><Select v-model="createDraft.status"><SelectTrigger id="reward-create-status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="active">上架</SelectItem><SelectItem value="inactive">停用</SelectItem></SelectContent></Select></div>
            <div class="grid gap-2"><Label for="reward-create-reason">变更原因</Label><Input id="reward-create-reason" v-model="createDraft.reason_code" /></div>
            <Button class="w-full" :disabled="busy || !canCreate" @click="createItem">{{ busy ? "处理中…" : "创建虚拟商品" }}</Button>
          </CardContent>
        </Card>

        <Card v-if="selected">
          <CardHeader><CardTitle>编辑商品</CardTitle><CardDescription>保存时会校验版本号并写入管理员审计日志。</CardDescription></CardHeader>
          <CardContent class="space-y-4">
            <div class="rounded-md bg-muted p-3 text-sm"><span class="text-muted-foreground">商品代码</span><strong class="ml-2">{{ selected.slug }}</strong><span class="ml-3 text-muted-foreground">当前版本 {{ selected.version }}</span></div>
            <div class="grid gap-2"><Label for="reward-edit-name">商品名称</Label><Input id="reward-edit-name" v-model="editDraft.name" maxlength="100" /></div>
            <div class="grid gap-2"><Label for="reward-edit-description">商品说明</Label><Textarea id="reward-edit-description" v-model="editDraft.description" maxlength="2000" class="min-h-24" /></div>
            <div class="grid gap-3 sm:grid-cols-3"><div class="grid gap-2"><Label for="reward-edit-cost">积分价格</Label><Input id="reward-edit-cost" v-model.number="editDraft.cost_points" type="number" min="1" /></div><div class="grid gap-2"><Label for="reward-edit-stock">库存</Label><Input id="reward-edit-stock" v-model.number="editDraft.stock" type="number" min="0" /></div><div class="grid gap-2"><Label for="reward-edit-limit">每人限购</Label><Input id="reward-edit-limit" v-model.number="editDraft.per_user_limit" type="number" min="1" /></div></div>
            <div class="grid gap-2"><Label for="reward-edit-status">状态</Label><Select v-model="editDraft.status"><SelectTrigger id="reward-edit-status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="active">上架</SelectItem><SelectItem value="inactive">停用</SelectItem></SelectContent></Select></div>
            <div class="grid gap-2"><Label for="reward-edit-reason">变更原因</Label><Input id="reward-edit-reason" v-model="editDraft.reason_code" /></div>
            <Button class="w-full" :disabled="busy || !canUpdate" @click="updateItem">保存商品</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  </section>
</template>
