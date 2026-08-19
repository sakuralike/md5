<script setup lang="ts">
import type {
  RewardAdminOrder,
  RewardOperationsStatsResponse,
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
  compensateAdminRewardOrder,
  createRewardCatalogKey,
  getAdminRewardOrder,
  getRewardOperationsStats,
  listAdminRewardOrders,
  retryAdminRewardOrder,
} from "../services/rewards";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const items = ref<RewardAdminOrder[]>([]);
const selected = ref<RewardAdminOrder | null>(null);
const stats = ref<RewardOperationsStatsResponse | null>(null);
const statusFilter = ref<RewardOrderStatus | "">("");
const actionReason = ref("fulfillment_reviewed");
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const message = ref("");

const canRetry = computed(
  () => selected.value?.status === "failed" && selected.value.compensated_at === null,
);
const canCompensate = computed(
  () => selected.value?.status === "failed" && selected.value.compensated_at === null,
);

function token(): string {
  if (!auth.accessToken) throw new Error("管理会话已失效，请重新登录");
  return auth.accessToken;
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

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function describeError(value: unknown): string {
  return value instanceof Error ? value.message : "商城订单操作失败";
}

async function load(selectId?: string): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [orders, operations] = await Promise.all([
      listAdminRewardOrders(statusFilter.value, token()),
      getRewardOperationsStats(token()),
    ]);
    items.value = orders.items;
    stats.value = operations;
    const targetId = selectId ?? selected.value?.id;
    if (targetId && orders.items.some((item) => item.id === targetId)) {
      selected.value = await getAdminRewardOrder(targetId, token());
    } else if (orders.items[0]) {
      selected.value = await getAdminRewardOrder(orders.items[0].id, token());
    } else {
      selected.value = null;
    }
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function openOrder(orderId: string): Promise<void> {
  error.value = "";
  message.value = "";
  try {
    selected.value = await getAdminRewardOrder(orderId, token());
  } catch (value) {
    error.value = describeError(value);
  }
}

async function applyAction(action: "retry" | "compensate"): Promise<void> {
  if (!selected.value) return;
  const reason = actionReason.value.trim();
  if (reason.length < 2) {
    error.value = "请填写操作原因码";
    return;
  }
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    const payload = { expected_version: selected.value.version, reason_code: reason };
    const order = action === "retry"
      ? await retryAdminRewardOrder(
          selected.value.id,
          payload,
          token(),
          createRewardCatalogKey("order-retry"),
        )
      : await compensateAdminRewardOrder(
          selected.value.id,
          payload,
          token(),
          createRewardCatalogKey("order-compensate"),
        );
    message.value = action === "retry" ? "订单已重新进入履约队列。" : "订单积分和库存已完成补偿。";
    await load(order.id);
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
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">积分商城 · 订单运营</p>
        <h1 class="text-2xl font-semibold tracking-tight">兑换订单工作台</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">查看订单、积分扣减、库存事件和履约时间线，并对最终失败订单执行受控重试或补偿。</p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load()">刷新订单</Button>
    </header>

    <div v-if="stats" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="商城运营指标">
      <Card><CardContent class="p-4"><p class="text-xs text-muted-foreground">订单总数</p><strong class="text-2xl">{{ stats.total_orders }}</strong></CardContent></Card>
      <Card><CardContent class="p-4"><p class="text-xs text-muted-foreground">待履约</p><strong class="text-2xl">{{ stats.pending_orders }}</strong></CardContent></Card>
      <Card><CardContent class="p-4"><p class="text-xs text-muted-foreground">已完成</p><strong class="text-2xl">{{ stats.fulfilled_orders }}</strong></CardContent></Card>
      <Card><CardContent class="p-4"><p class="text-xs text-muted-foreground">成功率</p><strong class="text-2xl">{{ stats.fulfillment_success_rate }}%</strong></CardContent></Card>
      <Card><CardContent class="p-4"><p class="text-xs text-muted-foreground">低库存商品</p><strong class="text-2xl">{{ stats.low_stock_items }}</strong></CardContent></Card>
    </div>

    <p v-if="error" class="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>
    <p v-if="message" class="rounded-md bg-primary/10 px-4 py-3 text-sm text-primary" role="status">{{ message }}</p>

    <div class="grid items-start gap-5 lg:grid-cols-[minmax(18rem,0.75fr)_minmax(0,1.25fr)]">
      <Card>
        <CardHeader class="flex flex-row items-center justify-between gap-3"><div><CardTitle>订单队列</CardTitle><CardDescription>{{ items.length }} 条当前结果</CardDescription></div><Select v-model="statusFilter" @update:model-value="load()"><SelectTrigger class="w-32" aria-label="订单状态筛选"><SelectValue placeholder="全部状态" /></SelectTrigger><SelectContent><SelectItem value="">全部状态</SelectItem><SelectItem value="pending_fulfillment">等待发放</SelectItem><SelectItem value="processing">发放中</SelectItem><SelectItem value="fulfilled">已完成</SelectItem><SelectItem value="failed">发放失败</SelectItem><SelectItem value="cancelled">已取消</SelectItem></SelectContent></Select></CardHeader>
        <CardContent class="space-y-3">
          <Button v-for="order in items" :key="order.id" variant="ghost" class="grid h-auto w-full gap-2 rounded-md border p-4 text-left" :class="selected?.id === order.id && 'border-primary bg-primary/5'" @click="openOrder(order.id)"><span class="flex w-full items-center justify-between gap-2"><strong>{{ order.item_name }}</strong><Badge variant="outline">{{ statusLabel(order.status) }}</Badge></span><span class="text-xs text-muted-foreground">{{ order.order_no }}</span><span class="text-sm">{{ order.total_cost_points }} 积分 · {{ order.quantity }} 件</span></Button>
          <p v-if="!loading && items.length === 0" class="py-8 text-center text-sm text-muted-foreground">当前筛选条件下没有订单。</p>
        </CardContent>
      </Card>

      <Card v-if="selected">
        <CardHeader><div class="flex flex-wrap items-center justify-between gap-3"><div><CardTitle>{{ selected.item_name }}</CardTitle><CardDescription>{{ selected.order_no }} · 用户 {{ selected.user_id }}</CardDescription></div><Badge>{{ statusLabel(selected.status) }}</Badge></div></CardHeader>
        <CardContent class="space-y-6">
          <dl class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><div><dt class="text-xs text-muted-foreground">扣减积分</dt><dd class="font-medium">{{ selected.total_cost_points }}</dd></div><div><dt class="text-xs text-muted-foreground">订单版本</dt><dd class="font-medium">{{ selected.version }}</dd></div><div><dt class="text-xs text-muted-foreground">创建时间</dt><dd class="font-medium">{{ formatTime(selected.created_at) }}</dd></div><div><dt class="text-xs text-muted-foreground">补偿时间</dt><dd class="font-medium">{{ formatTime(selected.compensated_at) }}</dd></div></dl>

          <section class="space-y-3"><h3 class="font-semibold">履约尝试</h3><div v-for="attempt in selected.fulfillments" :key="attempt.id" class="rounded-md border p-3 text-sm"><div class="flex items-center justify-between gap-3"><strong>第 {{ attempt.attempt_no }} 次</strong><Badge variant="outline">{{ attempt.status }}</Badge></div><p class="mt-1 text-muted-foreground">{{ attempt.safe_message || "等待后台工作进程处理" }} · 重试 {{ attempt.retry_count }} 次</p></div></section>

          <section class="space-y-3"><h3 class="font-semibold">库存事件</h3><div v-for="event in selected.inventory_events" :key="event.id" class="flex items-center justify-between gap-3 rounded-md border p-3 text-sm"><span>{{ event.reason_code }} · {{ event.stock_before }} → {{ event.stock_after }}</span><strong>{{ event.delta > 0 ? "+" : "" }}{{ event.delta }}</strong></div></section>

          <section class="space-y-3"><h3 class="font-semibold">订单时间线</h3><ol class="space-y-3 border-l pl-5"><li v-for="event in selected.timeline" :key="event.id" class="space-y-1"><strong>{{ event.event_type }}</strong><p class="text-sm text-muted-foreground">{{ event.reason_code }} · {{ statusLabel(event.to_status) }}</p><small class="text-muted-foreground">{{ formatTime(event.created_at) }}</small></li></ol></section>

          <section v-if="canRetry || canCompensate" class="space-y-3 border-t pt-4"><h3 class="font-semibold">失败订单处置</h3><div class="grid gap-2"><Label for="reward-order-action-reason">操作原因码</Label><Input id="reward-order-action-reason" v-model="actionReason" maxlength="100" /></div><div class="flex flex-col gap-2 sm:flex-row"><Button v-if="canRetry" :disabled="busy" @click="applyAction('retry')">重新履约</Button><Button v-if="canCompensate" variant="destructive" :disabled="busy" @click="applyAction('compensate')">退还积分与库存</Button></div></section>
        </CardContent>
      </Card>
      <Card v-else><CardContent class="p-8 text-center text-sm text-muted-foreground">请选择订单查看详情。</CardContent></Card>
    </div>
  </section>
</template>
