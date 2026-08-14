<script setup lang="ts">
import { ApiError } from "@password-detective/api-contract";
import type {
  FingerprintAlgorithm,
  HashPoolItem,
  HashPoolOverview,
} from "@password-detective/api-contract";
import { Database, Fingerprint, RefreshCw, Search, ShieldCheck } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { listHashPool } from "../services/hashPool";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const items = ref<HashPoolItem[]>([]);
const overview = ref<HashPoolOverview>({
  verified_candidates: 0,
  unique_archives: 0,
  unique_fingerprints: 0,
  pending_candidates: 0,
  quarantined_candidates: 0,
});
const query = ref("");
const algorithm = ref<FingerprintAlgorithm | "all">("all");
const page = ref(1);
const pageSize = 20;
const total = ref(0);
const loading = ref(false);
const error = ref("");

const algorithmLabels: Record<FingerprintAlgorithm, string> = {
  md5: "MD5",
  sha1: "SHA-1",
  sha256: "SHA-256",
  sha512: "SHA-512",
};

function describeError(value: unknown): string {
  if (value instanceof ApiError) return value.message;
  if (value instanceof Error) return value.message;
  return "总哈希池加载失败，请稍后重试。";
}

async function loadPool(resetPage = false): Promise<void> {
  if (!auth.accessToken) return;
  if (resetPage) page.value = 1;
  loading.value = true;
  error.value = "";
  try {
    const response = await listHashPool(
      {
        query: query.value,
        algorithm: algorithm.value === "all" ? "" : algorithm.value,
        page: page.value,
        pageSize,
      },
      auth.accessToken,
    );
    items.value = response.items;
    overview.value = response.overview;
    total.value = response.total;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

function formatDate(value: string | null): string {
  if (!value) return "未记录";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function previousPage(): void {
  if (page.value <= 1) return;
  page.value -= 1;
  void loadPool();
}

function nextPage(): void {
  if (page.value * pageSize >= total.value) return;
  page.value += 1;
  void loadPool();
}

onMounted(() => loadPool(true));
</script>

<template>
  <section class="space-y-6">
    <header class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
          已验证数据资产
        </p>
        <h1 class="text-2xl font-semibold tracking-tight">总哈希池</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          汇总已通过自动证据规则或人工复核的候选记录，按指纹检索并监控待验证、隔离队列规模。
        </p>
      </div>
      <aside class="max-w-md rounded-lg border border-primary/30 bg-primary/10 p-4 text-sm">
        <div class="flex items-center gap-2 font-semibold text-primary">
          <ShieldCheck class="h-4 w-4" /> 最小披露
        </div>
        <p class="mt-2 leading-6 text-muted-foreground">
          此页面仅展示存档哈希、证据数量与验证时间，不返回或解密候选密码。
        </p>
      </aside>
    </header>

    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <article
        v-for="metric in [
          ['已验证候选', overview.verified_candidates],
          ['唯一存档', overview.unique_archives],
          ['唯一指纹', overview.unique_fingerprints],
          ['待验证', overview.pending_candidates],
          ['隔离中', overview.quarantined_candidates],
        ]"
        :key="String(metric[0])"
        class="rounded-lg border bg-card p-4 text-card-foreground shadow-sm"
      >
        <p class="text-sm text-muted-foreground">{{ metric[0] }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ metric[1] }}</p>
      </article>
    </div>

    <form
      class="grid gap-4 rounded-lg border bg-card p-4 md:grid-cols-[minmax(16rem,1fr)_minmax(10rem,0.35fr)_auto] md:items-end"
      aria-label="总哈希池筛选"
      @submit.prevent="loadPool(true)"
    >
      <Label class="grid gap-2">
        <span>候选 ID、存档 ID 或哈希片段</span>
        <Input v-model="query" placeholder="输入哈希片段进行检索" />
      </Label>
      <Label class="grid gap-2">
        <span>指纹算法</span>
        <Select v-model="algorithm">
          <SelectTrigger aria-label="指纹算法"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部算法</SelectItem>
            <SelectItem value="md5">MD5</SelectItem>
            <SelectItem value="sha1">SHA-1</SelectItem>
            <SelectItem value="sha256">SHA-256</SelectItem>
            <SelectItem value="sha512">SHA-512</SelectItem>
          </SelectContent>
        </Select>
      </Label>
      <div class="flex gap-2">
        <Button type="submit" :disabled="loading"><Search class="mr-2 h-4 w-4" />查询</Button>
        <Button type="button" variant="outline" :disabled="loading" @click="loadPool()">
          <RefreshCw class="mr-2 h-4 w-4" />刷新
        </Button>
      </div>
    </form>

    <div v-if="error" class="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" role="alert">
      {{ error }}
    </div>

    <div class="overflow-hidden rounded-lg border bg-card shadow-sm">
      <div v-if="loading" class="p-8 text-center text-sm text-muted-foreground">正在加载总哈希池…</div>
      <div v-else-if="items.length === 0" class="p-10 text-center">
        <Database class="mx-auto h-10 w-10 text-muted-foreground" />
        <p class="mt-3 font-medium">没有符合条件的已验证记录</p>
        <p class="mt-1 text-sm text-muted-foreground">可清空筛选条件后重新查询。</p>
      </div>
      <div v-else class="divide-y">
        <article v-for="item in items" :key="item.candidate_id" class="space-y-4 p-5">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div class="min-w-0 space-y-1">
              <div class="flex items-center gap-2">
                <Fingerprint class="h-4 w-4 text-primary" />
                <h2 class="font-semibold">候选 {{ item.candidate_id }}</h2>
              </div>
              <p class="break-all text-xs text-muted-foreground">存档 {{ item.archive_id }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <Badge variant="secondary">置信度 {{ Math.round(item.confidence_score * 100) }}%</Badge>
              <Badge variant="outline">提交 {{ item.submission_count }}</Badge>
              <Badge variant="outline">反馈 {{ item.feedback_count }}</Badge>
            </div>
          </div>
          <div class="grid gap-2">
            <div
              v-for="fingerprint in item.fingerprints"
              :key="`${fingerprint.algorithm}:${fingerprint.digest}`"
              class="grid gap-1 rounded-md bg-muted p-3 text-xs sm:grid-cols-[5rem_1fr]"
            >
              <strong>{{ algorithmLabels[fingerprint.algorithm] }}</strong>
              <code class="break-all text-muted-foreground">{{ fingerprint.digest }}</code>
            </div>
          </div>
          <p class="text-xs text-muted-foreground">最近验证：{{ formatDate(item.last_verified_at) }}</p>
        </article>
      </div>
    </div>

    <footer class="flex items-center justify-between text-sm text-muted-foreground">
      <span>第 {{ page }} 页，共 {{ total }} 条</span>
      <div class="flex gap-2">
        <Button variant="outline" size="sm" :disabled="page <= 1 || loading" @click="previousPage">上一页</Button>
        <Button variant="outline" size="sm" :disabled="page * pageSize >= total || loading" @click="nextPage">下一页</Button>
      </div>
    </footer>
  </section>
</template>
