<script setup lang="ts">
import type { RewardCatalogResponse, RewardStockStatus } from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getRewardCatalog } from "../services/rewards";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const data = ref<RewardCatalogResponse | null>(null);
const loading = ref(true);
const error = ref("");

function stockLabel(status: RewardStockStatus): string {
  return { available: "库存充足", limited: "库存紧张", out_of_stock: "暂时缺货" }[status];
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    data.value = await getRewardCatalog(auth.isAuthenticated ? auth.accessToken : undefined);
  } catch (value) {
    error.value = value instanceof Error ? value.message : "商城目录加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => void load());
</script>

<template>
  <main class="mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
    <header class="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2"><div class="flex items-center gap-2 text-sm font-medium text-primary"><Badge>积分商城</Badge><span>虚拟权益目录</span></div><h1 class="text-3xl font-semibold tracking-tight">积分商城</h1><p class="max-w-3xl text-sm leading-6 text-muted-foreground">浏览使用已结算积分兑换的虚拟权益。订单、扣积分和履约功能将在目录治理稳定后开放。</p></div>
      <div class="flex items-center gap-3"><div v-if="data?.available_points !== null && data?.available_points !== undefined" class="rounded-md border bg-card px-4 py-3 text-right"><p class="text-xs text-muted-foreground">可用积分</p><p class="font-semibold">{{ data.available_points }}</p></div><Button variant="outline" :disabled="loading" @click="load">刷新</Button></div>
    </header>

    <p v-if="error" class="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>
    <div v-if="loading" class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3"><div v-for="index in 3" :key="index" class="h-48 animate-pulse rounded-xl bg-muted" /></div>
    <section v-else-if="data" class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3" aria-label="虚拟商品目录">
      <Card v-for="item in data.items" :key="item.id" class="flex flex-col">
        <CardHeader><div class="flex items-start justify-between gap-3"><CardTitle class="text-lg">{{ item.name }}</CardTitle><Badge variant="secondary">虚拟权益</Badge></div><CardDescription>{{ item.description }}</CardDescription></CardHeader>
        <CardContent class="mt-auto space-y-4"><div class="flex items-end justify-between gap-3"><div><p class="text-xs text-muted-foreground">兑换所需</p><p class="text-2xl font-semibold">{{ item.cost_points }} <span class="text-sm font-normal text-muted-foreground">积分</span></p></div><Badge :variant="item.stock_status === 'out_of_stock' ? 'outline' : item.stock_status === 'limited' ? 'default' : 'secondary'">{{ stockLabel(item.stock_status) }}</Badge></div><p class="text-xs text-muted-foreground">每位用户最多兑换 {{ item.per_user_limit }} 件</p><Button class="w-full" variant="outline" disabled>兑换功能即将开放</Button></CardContent>
      </Card>
      <p v-if="data.items.length === 0" class="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground sm:col-span-2 lg:col-span-3">暂无上架商品。</p>
    </section>
  </main>
</template>
