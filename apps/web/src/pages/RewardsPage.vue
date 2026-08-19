<script setup lang="ts">
import type {
  RewardCatalogItem,
  RewardCatalogResponse,
  RewardOrderSummary,
  RewardOrderStatus,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  cancelRewardOrder,
  createRewardOrder,
  createRewardOrderKey,
  getRewardCatalog,
  listRewardOrders,
} from "../services/rewards";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const data = ref<RewardCatalogResponse | null>(null);
const orders = ref<RewardOrderSummary[]>([]);
const loading = ref(true);
const busyId = ref("");
const error = ref("");
const message = ref("");
const selectedCategory = ref("");
const selectedTag = ref("");
const quantityByItem = ref<Record<string, number>>({});

const visibleItems = computed(() => {
  return (data.value?.items ?? []).filter((item) => {
    const categoryMatches = !selectedCategory.value || item.category === selectedCategory.value;
    const tagMatches = !selectedTag.value || item.tags.includes(selectedTag.value);
    return categoryMatches && tagMatches;
  });
});

function stockLabel(status: RewardCatalogItem["stock_status"]): string {
  return { available: "库存充足", limited: "库存紧张", out_of_stock: "暂时缺货" }[status];
}

function statusLabel(value: RewardOrderStatus): string {
  return {
    pending_fulfillment: "等待发放",
    processing: "发放中",
    fulfilled: "已完成",
    failed: "发放失败",
    cancelled: "已取消",
  }[value];
}

function redeemLabel(item: RewardCatalogItem): string {
  if (item.redeem_status === "scheduled") return "尚未开始";
  if (item.redeem_status === "ended") return "兑换已结束";
  if (item.redeem_status === "out_of_stock") return "暂时缺货";
  return "兑换";
}

function quantity(item: RewardCatalogItem): number {
  return quantityByItem.value[item.id] ?? 1;
}

function setQuantity(item: RewardCatalogItem, value: number): void {
  quantityByItem.value[item.id] = Math.max(1, Math.min(10, Math.trunc(value || 1)));
}

function describeError(value: unknown): string {
  return value instanceof Error ? value.message : "商城操作失败";
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [catalog, orderData] = await Promise.all([
      getRewardCatalog(auth.isAuthenticated ? auth.accessToken : undefined),
      auth.isAuthenticated ? listRewardOrders(auth.accessToken) : Promise.resolve(null),
    ]);
    data.value = catalog;
    orders.value = orderData?.items ?? [];
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function redeem(item: RewardCatalogItem): Promise<void> {
  if (!auth.isAuthenticated) {
    error.value = "请先登录后再兑换商品";
    return;
  }
  if (item.redeem_status !== "available") return;
  busyId.value = item.id;
  error.value = "";
  message.value = "";
  try {
    const order = await createRewardOrder(
      { catalog_item_id: item.id, quantity: quantity(item) },
      auth.accessToken,
      createRewardOrderKey(),
    );
    message.value = `订单 ${order.order_no} 已创建，积分已扣除，权益将自动发放。`;
    await load();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busyId.value = "";
  }
}

async function cancel(order: RewardOrderSummary): Promise<void> {
  if (order.status !== "pending_fulfillment") return;
  busyId.value = order.id;
  error.value = "";
  try {
    await cancelRewardOrder(order.id, auth.accessToken, `reward-cancel-${order.id}-${Date.now()}`);
    message.value = `订单 ${order.order_no} 已取消，积分和库存已返还。`;
    await load();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busyId.value = "";
  }
}

onMounted(() => void load());
</script>

<template>
  <main class="mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
    <header class="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <div class="flex items-center gap-2 text-sm font-medium text-primary">
          <Badge>积分商城</Badge><span>虚拟权益目录</span>
        </div>
        <h1 class="text-3xl font-semibold tracking-tight">积分商城</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          使用已结算积分兑换虚拟权益，订单和发放状态可以在当前页面追踪。
        </p>
      </div>
      <div class="flex items-center gap-3">
        <div v-if="data?.available_points !== null && data?.available_points !== undefined" class="rounded-md border bg-card px-4 py-3 text-right">
          <p class="text-xs text-muted-foreground">可用积分</p><p class="font-semibold">{{ data.available_points }}</p>
        </div>
        <Button variant="outline" :disabled="loading" @click="load">刷新</Button>
      </div>
    </header>

    <p v-if="error" class="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>
    <p v-if="message" class="rounded-md bg-primary/10 px-4 py-3 text-sm text-primary" role="status">{{ message }}</p>

    <section v-if="data" class="flex flex-wrap items-center gap-3" aria-label="商城筛选">
      <Label for="reward-category" class="text-sm text-muted-foreground">分类</Label>
      <Select v-model="selectedCategory">
        <SelectTrigger id="reward-category" class="w-32"><SelectValue placeholder="全部分类" /></SelectTrigger>
        <SelectContent><SelectItem value="">全部分类</SelectItem><SelectItem v-for="category in data.categories" :key="category" :value="category">{{ category }}</SelectItem></SelectContent>
      </Select>
      <Label for="reward-tag" class="text-sm text-muted-foreground">标签</Label>
      <Select v-model="selectedTag">
        <SelectTrigger id="reward-tag" class="w-32"><SelectValue placeholder="全部标签" /></SelectTrigger>
        <SelectContent><SelectItem value="">全部标签</SelectItem><SelectItem v-for="tag in data.tags" :key="tag" :value="tag">{{ tag }}</SelectItem></SelectContent>
      </Select>
    </section>

    <section v-if="loading" class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3"><div v-for="index in 3" :key="index" class="h-56 animate-pulse rounded-xl bg-muted" /></section>
    <section v-else-if="data" class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3" aria-label="虚拟商品目录">
      <Card v-for="item in visibleItems" :key="item.id" class="flex flex-col">
        <CardHeader>
          <div class="flex items-start justify-between gap-3"><CardTitle class="text-lg">{{ item.name }}</CardTitle><Badge variant="secondary">虚拟权益</Badge></div>
          <CardDescription>{{ item.description }}</CardDescription>
          <div class="flex flex-wrap gap-1.5"><Badge v-for="tag in item.tags" :key="tag" variant="outline">{{ tag }}</Badge></div>
        </CardHeader>
        <CardContent class="mt-auto space-y-4">
          <div class="flex items-end justify-between gap-3"><div><p class="text-xs text-muted-foreground">兑换所需</p><p class="text-2xl font-semibold">{{ item.cost_points }} <span class="text-sm font-normal text-muted-foreground">积分</span></p></div><Badge :variant="item.stock_status === 'out_of_stock' ? 'outline' : 'secondary'">{{ stockLabel(item.stock_status) }}</Badge></div>
          <p class="text-xs text-muted-foreground">每位用户最多兑换 {{ item.per_user_limit }} 件 · 权益 {{ item.entitlement_duration_days ? `${item.entitlement_duration_days} 天` : "长期" }}</p>
          <div v-if="auth.isAuthenticated" class="flex items-center gap-2"><Label :for="`quantity-${item.id}`" class="text-xs text-muted-foreground">数量</Label><Input :id="`quantity-${item.id}`" :model-value="quantity(item)" type="number" min="1" max="10" class="w-20" @update:model-value="setQuantity(item, Number($event))" /><Button class="flex-1" :disabled="busyId === item.id || item.redeem_status !== 'available'" @click="redeem(item)">{{ busyId === item.id ? "处理中" : redeemLabel(item) }}</Button></div>
          <Button v-else class="w-full" variant="outline" @click="redeem(item)">{{ redeemLabel(item) }}</Button>
        </CardContent>
      </Card>
      <p v-if="visibleItems.length === 0" class="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground sm:col-span-2 lg:col-span-3">暂无符合条件的商品。</p>
    </section>

    <section v-if="auth.isAuthenticated" class="space-y-4" aria-label="我的兑换订单">
      <div class="flex items-end justify-between gap-3"><div><h2 class="text-xl font-semibold">我的订单</h2><p class="text-sm text-muted-foreground">订单会保留商品和积分快照，商品下架后仍可查询。</p></div><Button variant="outline" :disabled="loading" @click="load">刷新订单</Button></div>
      <template v-if="orders.length">
        <Card v-for="order in orders" :key="order.id"><CardContent class="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between"><div class="space-y-1"><div class="flex flex-wrap items-center gap-2"><strong>{{ order.item_name }}</strong><Badge variant="outline">{{ statusLabel(order.status) }}</Badge></div><p class="text-sm text-muted-foreground">{{ order.order_no }} · {{ order.total_cost_points }} 积分 · {{ new Date(order.created_at).toLocaleString() }}</p><p v-if="order.fulfillment?.safe_message" class="text-sm text-muted-foreground">{{ order.fulfillment.safe_message }}</p></div><Button v-if="order.status === 'pending_fulfillment'" variant="outline" :disabled="busyId === order.id" @click="cancel(order)">{{ busyId === order.id ? "处理中" : "取消订单" }}</Button></CardContent></Card>
      </template>
      <p v-else class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">暂无兑换订单。</p>
    </section>
  </main>
</template>
