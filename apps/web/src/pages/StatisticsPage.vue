<script setup lang="ts">
import type { AlgorithmDistributionResponse } from "@password-detective/api-contract";
import { BarChart3, RefreshCw, ShieldCheck } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { getAlgorithmDistribution } from "../services/site";

const data = ref<AlgorithmDistributionResponse | null>(null);
const loading = ref(false);
const error = ref("");
const algorithmLabels = { md5: "MD5", sha1: "SHA-1", sha256: "SHA-256", sha512: "SHA-512" } as const;

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    data.value = await getAlgorithmDistribution();
  } catch (value) {
    error.value = value instanceof Error ? value.message : "统计数据暂时不可用";
  } finally {
    loading.value = false;
  }
}

onMounted(() => void load());
</script>

<template>
  <main class="mx-auto w-full max-w-5xl space-y-8 px-4 py-8 sm:px-6">
    <header class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div class="space-y-2">
        <div class="flex items-center gap-2 text-sm font-medium text-primary">
          <BarChart3 class="h-4 w-4" />公开数据统计
        </div>
        <h1 class="text-3xl font-semibold">算法分布</h1>
        <p class="max-w-2xl text-sm leading-6 text-muted-foreground">
          仅聚合已验证公开档案的指纹算法，不包含待验证、隔离记录或任何候选密码。
        </p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load">
        <RefreshCw class="mr-2 h-4 w-4" :class="loading && 'animate-spin'" />刷新
      </Button>
    </header>

    <p v-if="error" class="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>

    <section class="space-y-5 border-y py-6" aria-labelledby="distribution-heading">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="distribution-heading" class="text-lg font-semibold">公开指纹池</h2>
          <p class="mt-1 text-sm text-muted-foreground">总量区间：{{ data?.total_count_band ?? "读取中" }}</p>
        </div>
        <Badge variant="secondary"><ShieldCheck class="mr-1 h-3.5 w-3.5" />隐私聚合</Badge>
      </div>
      <div v-if="loading && !data" class="space-y-4" aria-label="正在加载算法分布">
        <div v-for="index in 4" :key="index" class="h-14 animate-pulse rounded-md bg-muted" />
      </div>
      <div v-else-if="data" class="space-y-5">
        <div v-for="item in data.items" :key="item.algorithm" class="space-y-2">
          <div class="flex items-center justify-between gap-4 text-sm">
            <span class="font-medium">{{ algorithmLabels[item.algorithm] }}</span>
            <span class="text-muted-foreground">{{ item.count_band }} · {{ item.percentage }}%</span>
          </div>
          <Progress :model-value="item.percentage" :aria-label="`${algorithmLabels[item.algorithm]} 占比 ${item.percentage}%`" />
        </div>
      </div>
    </section>
  </main>
</template>
