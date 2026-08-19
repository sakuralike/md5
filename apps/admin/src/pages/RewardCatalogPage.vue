<script setup lang="ts">
import type {
  AdminRewardCatalogItem,
  RewardCatalogCreateRequest,
  RewardCatalogStatus,
  RewardCatalogUpdateRequest,
  RewardInventoryAdjustmentRequest,
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
  adjustAdminRewardInventory,
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
  category: string;
  tags: string;
  sort_weight: number;
  entitlement_key: string;
  entitlement_duration_days: number;
  redeem_start_at: string;
  redeem_end_at: string;
  status: RewardCatalogStatus;
  reason_code: string;
}

const auth = useAdminAuthStore();
const items = ref<AdminRewardCatalogItem[]>([]);
const selectedId = ref("");
const statusFilter = ref<RewardCatalogStatus | "">("");
const createDraft = ref<CatalogDraft>(emptyDraft());
const editDraft = ref<CatalogDraft>(emptyDraft());
const inventoryDelta = ref(0);
const inventoryReason = ref<RewardInventoryAdjustmentRequest["reason_code"]>("restock");
const inventoryNote = ref("");
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const message = ref("");

const selected = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null);
const canCreate = computed(
  () => createDraft.value.slug.trim().length >= 3 && createDraft.value.name.trim().length >= 2,
);
const canUpdate = computed(() => selected.value !== null && editDraft.value.name.trim().length >= 2);
const canAdjustInventory = computed(() => selected.value !== null && inventoryDelta.value !== 0);

function emptyDraft(): CatalogDraft {
  return {
    slug: "",
    name: "",
    description: "",
    cost_points: 100,
    stock: 100,
    per_user_limit: 1,
    category: "general",
    tags: "",
    sort_weight: 0,
    entitlement_key: "community_supporter",
    entitlement_duration_days: 0,
    redeem_start_at: "",
    redeem_end_at: "",
    status: "draft",
    reason_code: "catalog_initial_setup",
  };
}

function requireToken(): string {
  if (!auth.accessToken) throw new Error("管理会话已失效，请重新登录");
  return auth.accessToken;
}

function toIso(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

function fromIso(value: string | null): string {
  return value ? value.slice(0, 16) : "";
}

function draftFromItem(item: AdminRewardCatalogItem): CatalogDraft {
  return {
    slug: item.slug,
    name: item.name,
    description: item.description,
    cost_points: item.cost_points,
    stock: item.stock,
    per_user_limit: item.per_user_limit,
    category: item.category,
    tags: item.tags.join(", "),
    sort_weight: item.sort_weight,
    entitlement_key: item.entitlement_key,
    entitlement_duration_days: item.entitlement_duration_days ?? 0,
    redeem_start_at: fromIso(item.redeem_start_at),
    redeem_end_at: fromIso(item.redeem_end_at),
    status: item.status,
    reason_code: "catalog_update",
  };
}

function selectItem(item: AdminRewardCatalogItem): void {
  selectedId.value = item.id;
  editDraft.value = draftFromItem(item);
  inventoryDelta.value = 0;
  inventoryNote.value = "";
  error.value = "";
  message.value = "";
}

function statusLabel(value: RewardCatalogStatus): string {
  return { draft: "草稿", active: "上架", inactive: "停用" }[value];
}

function stockLabel(stock: number): string {
  return stock === 0 ? "无库存" : stock < 10 ? "库存紧张" : "库存充足";
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

function createPayload(): RewardCatalogCreateRequest {
  return {
    slug: createDraft.value.slug.trim().toLowerCase(),
    name: createDraft.value.name.trim(),
    description: createDraft.value.description.trim(),
    kind: "virtual",
    cost_points: Number(createDraft.value.cost_points),
    stock: Number(createDraft.value.stock),
    per_user_limit: Number(createDraft.value.per_user_limit),
    category: createDraft.value.category.trim().toLowerCase(),
    tags: createDraft.value.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
    sort_weight: Number(createDraft.value.sort_weight),
    entitlement_key: createDraft.value.entitlement_key.trim(),
    entitlement_duration_days: createDraft.value.entitlement_duration_days
      ? Number(createDraft.value.entitlement_duration_days)
      : null,
    redeem_start_at: toIso(createDraft.value.redeem_start_at),
    redeem_end_at: toIso(createDraft.value.redeem_end_at),
    status: createDraft.value.status,
    reason_code: createDraft.value.reason_code.trim(),
  };
}

async function createItem(): Promise<void> {
  if (!canCreate.value) return;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    const item = await createAdminRewardCatalog(
      createPayload(),
      requireToken(),
      createRewardCatalogKey("create"),
    );
    createDraft.value = emptyDraft();
    message.value = `商品“${item.name}”已创建。`;
    await load();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

function updatePayload(): RewardCatalogUpdateRequest {
  return {
    name: editDraft.value.name.trim(),
    description: editDraft.value.description.trim(),
    kind: "virtual",
    cost_points: Number(editDraft.value.cost_points),
    per_user_limit: Number(editDraft.value.per_user_limit),
    category: editDraft.value.category.trim().toLowerCase(),
    tags: editDraft.value.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
    sort_weight: Number(editDraft.value.sort_weight),
    entitlement_key: editDraft.value.entitlement_key.trim(),
    entitlement_duration_days: editDraft.value.entitlement_duration_days
      ? Number(editDraft.value.entitlement_duration_days)
      : null,
    redeem_start_at: toIso(editDraft.value.redeem_start_at),
    redeem_end_at: toIso(editDraft.value.redeem_end_at),
    status: editDraft.value.status,
    expected_version: selected.value?.version ?? 0,
    reason_code: editDraft.value.reason_code.trim(),
  };
}

async function updateItem(): Promise<void> {
  if (!selected.value || !canUpdate.value) return;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    const item = await updateAdminRewardCatalog(
      selected.value.id,
      updatePayload(),
      requireToken(),
      createRewardCatalogKey("update"),
    );
    message.value = `商品“${item.name}”已更新，库存请使用独立调整。`;
    await load();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

async function adjustInventory(): Promise<void> {
  if (!selected.value || !canAdjustInventory.value) return;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    const item = await adjustAdminRewardInventory(
      selected.value.id,
      {
        delta: Number(inventoryDelta.value),
        reason_code: inventoryReason.value,
        expected_version: selected.value.version,
        note: inventoryNote.value.trim() || null,
      },
      requireToken(),
      createRewardCatalogKey("inventory"),
    );
    inventoryDelta.value = 0;
    inventoryNote.value = "";
    message.value = `库存已调整为 ${item.stock} 件。`;
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
          管理虚拟权益目录、兑换时间窗和运营库存。订单会记录商品快照，库存只能通过独立事件调整。
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
            <div class="min-w-0 space-y-1"><div class="flex flex-wrap items-center gap-2"><strong class="truncate">{{ item.name }}</strong><Badge variant="outline">{{ statusLabel(item.status) }}</Badge><Badge variant="secondary">{{ item.category }}</Badge></div><p class="line-clamp-2 text-sm text-muted-foreground">{{ item.description }}</p><p class="text-xs text-muted-foreground">{{ item.slug }} · 版本 {{ item.version }}</p></div>
            <div class="text-left text-sm sm:text-right"><strong>{{ item.cost_points }} 积分</strong><p class="text-xs text-muted-foreground">{{ stockLabel(item.stock) }} · {{ item.stock }} 件</p><p class="text-xs text-muted-foreground">每人限 {{ item.per_user_limit }} 件</p></div>
          </Button>
          <p v-if="!loading && items.length === 0" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">暂无商品，请从右侧创建虚拟商品。</p>
        </CardContent>
      </Card>

      <div class="space-y-5">
        <Card>
          <CardHeader><CardTitle>创建商品</CardTitle><CardDescription>商品代码创建后不可修改，商品类型固定为虚拟权益。</CardDescription></CardHeader>
          <CardContent class="space-y-4">
            <div class="grid gap-2"><Label for="reward-create-slug">商品代码</Label><Input id="reward-create-slug" v-model="createDraft.slug" placeholder="synthetic-reward" /></div>
            <div class="grid gap-2"><Label for="reward-create-name">商品名称</Label><Input id="reward-create-name" v-model="createDraft.name" maxlength="100" /></div>
            <div class="grid gap-2"><Label for="reward-create-description">商品说明</Label><Textarea id="reward-create-description" v-model="createDraft.description" maxlength="2000" class="min-h-24" /></div>
            <div class="grid gap-3 sm:grid-cols-3"><div class="grid gap-2"><Label for="reward-create-cost">积分价格</Label><Input id="reward-create-cost" v-model.number="createDraft.cost_points" type="number" min="1" /></div><div class="grid gap-2"><Label for="reward-create-stock">初始库存</Label><Input id="reward-create-stock" v-model.number="createDraft.stock" type="number" min="0" /></div><div class="grid gap-2"><Label for="reward-create-limit">每人限购</Label><Input id="reward-create-limit" v-model.number="createDraft.per_user_limit" type="number" min="1" /></div></div>
            <div class="grid gap-3 sm:grid-cols-2"><div class="grid gap-2"><Label for="reward-create-category">分类</Label><Input id="reward-create-category" v-model="createDraft.category" /></div><div class="grid gap-2"><Label for="reward-create-tags">标签</Label><Input id="reward-create-tags" v-model="createDraft.tags" placeholder="featured, community" /></div></div>
            <div class="grid gap-3 sm:grid-cols-3"><div class="grid gap-2"><Label for="reward-create-entitlement">权益标识</Label><Select v-model="createDraft.entitlement_key"><SelectTrigger id="reward-create-entitlement"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="community_supporter">社区支持者</SelectItem><SelectItem value="priority_case_review">优先案件复核</SelectItem><SelectItem value="daily_reveal_boost">每日揭示加成</SelectItem></SelectContent></Select></div><div class="grid gap-2"><Label for="reward-create-duration">有效天数</Label><Input id="reward-create-duration" v-model.number="createDraft.entitlement_duration_days" type="number" min="0" /></div><div class="grid gap-2"><Label for="reward-create-weight">排序权重</Label><Input id="reward-create-weight" v-model.number="createDraft.sort_weight" type="number" /></div></div>
            <div class="grid gap-3 sm:grid-cols-2"><div class="grid gap-2"><Label for="reward-create-start">兑换开始时间</Label><Input id="reward-create-start" v-model="createDraft.redeem_start_at" type="datetime-local" /></div><div class="grid gap-2"><Label for="reward-create-end">兑换结束时间</Label><Input id="reward-create-end" v-model="createDraft.redeem_end_at" type="datetime-local" /></div></div>
            <div class="grid gap-2"><Label for="reward-create-status">初始状态</Label><Select v-model="createDraft.status"><SelectTrigger id="reward-create-status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="active">上架</SelectItem><SelectItem value="inactive">停用</SelectItem></SelectContent></Select></div>
            <div class="grid gap-2"><Label for="reward-create-reason">变更原因</Label><Input id="reward-create-reason" v-model="createDraft.reason_code" /></div>
            <Button class="w-full" :disabled="busy || !canCreate" @click="createItem">{{ busy ? "处理中…" : "创建虚拟商品" }}</Button>
          </CardContent>
        </Card>

        <Card v-if="selected">
          <CardHeader><CardTitle>编辑商品</CardTitle><CardDescription>保存商品信息不会覆盖库存，库存必须通过受控增量事件调整。</CardDescription></CardHeader>
          <CardContent class="space-y-4">
            <div class="rounded-md bg-muted p-3 text-sm"><span class="text-muted-foreground">商品代码</span><strong class="ml-2">{{ selected.slug }}</strong><span class="ml-3 text-muted-foreground">当前版本 {{ selected.version }}</span></div>
            <div class="grid gap-2"><Label for="reward-edit-name">商品名称</Label><Input id="reward-edit-name" v-model="editDraft.name" maxlength="100" /></div>
            <div class="grid gap-2"><Label for="reward-edit-description">商品说明</Label><Textarea id="reward-edit-description" v-model="editDraft.description" maxlength="2000" class="min-h-24" /></div>
            <div class="grid gap-3 sm:grid-cols-2"><div class="grid gap-2"><Label for="reward-edit-cost">积分价格</Label><Input id="reward-edit-cost" v-model.number="editDraft.cost_points" type="number" min="1" /></div><div class="grid gap-2"><Label for="reward-edit-limit">每人限购</Label><Input id="reward-edit-limit" v-model.number="editDraft.per_user_limit" type="number" min="1" /></div></div>
            <div class="grid gap-3 sm:grid-cols-2"><div class="grid gap-2"><Label for="reward-edit-category">分类</Label><Input id="reward-edit-category" v-model="editDraft.category" /></div><div class="grid gap-2"><Label for="reward-edit-tags">标签</Label><Input id="reward-edit-tags" v-model="editDraft.tags" /></div></div>
            <div class="grid gap-3 sm:grid-cols-3"><div class="grid gap-2"><Label for="reward-edit-entitlement">权益标识</Label><Select v-model="editDraft.entitlement_key"><SelectTrigger id="reward-edit-entitlement"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="community_supporter">社区支持者</SelectItem><SelectItem value="priority_case_review">优先案件复核</SelectItem><SelectItem value="daily_reveal_boost">每日揭示加成</SelectItem></SelectContent></Select></div><div class="grid gap-2"><Label for="reward-edit-duration">有效天数</Label><Input id="reward-edit-duration" v-model.number="editDraft.entitlement_duration_days" type="number" min="0" /></div><div class="grid gap-2"><Label for="reward-edit-weight">排序权重</Label><Input id="reward-edit-weight" v-model.number="editDraft.sort_weight" type="number" /></div></div>
            <div class="grid gap-3 sm:grid-cols-2"><div class="grid gap-2"><Label for="reward-edit-start">兑换开始时间</Label><Input id="reward-edit-start" v-model="editDraft.redeem_start_at" type="datetime-local" /></div><div class="grid gap-2"><Label for="reward-edit-end">兑换结束时间</Label><Input id="reward-edit-end" v-model="editDraft.redeem_end_at" type="datetime-local" /></div></div>
            <div class="grid gap-2"><Label for="reward-edit-status">状态</Label><Select v-model="editDraft.status"><SelectTrigger id="reward-edit-status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="active">上架</SelectItem><SelectItem value="inactive">停用</SelectItem></SelectContent></Select></div>
            <div class="grid gap-2"><Label for="reward-edit-reason">变更原因</Label><Input id="reward-edit-reason" v-model="editDraft.reason_code" /></div>
            <Button class="w-full" :disabled="busy || !canUpdate" @click="updateItem">保存商品</Button>
            <div class="space-y-3 border-t pt-4"><div><h3 class="font-medium">库存调整</h3><p class="text-sm text-muted-foreground">当前库存 {{ selected.stock }} 件；正数补库存，负数扣减。</p></div><div class="grid gap-3 sm:grid-cols-2"><div class="grid gap-2"><Label for="reward-inventory-delta">调整数量</Label><Input id="reward-inventory-delta" v-model.number="inventoryDelta" type="number" /></div><div class="grid gap-2"><Label for="reward-inventory-reason">调整原因</Label><Select v-model="inventoryReason"><SelectTrigger id="reward-inventory-reason"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="restock">补货</SelectItem><SelectItem value="correction">盘点修正</SelectItem><SelectItem value="campaign">活动库存</SelectItem></SelectContent></Select></div></div><div class="grid gap-2"><Label for="reward-inventory-note">备注</Label><Input id="reward-inventory-note" v-model="inventoryNote" maxlength="300" /></div><Button variant="outline" class="w-full" :disabled="busy || !canAdjustInventory" @click="adjustInventory">保存库存调整</Button></div>
          </CardContent>
        </Card>
      </div>
    </div>
  </section>
</template>
