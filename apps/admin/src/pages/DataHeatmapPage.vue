<script setup lang="ts">
import type { AdminCommunityHeatmapResponse } from "@password-detective/api-contract";
import { Activity, RefreshCw, ShieldCheck } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getCommunityHeatmap } from "../services/analytics";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const data = ref<AdminCommunityHeatmapResponse | null>(null);
const windowDays = ref("30");
const loading = ref(false);
const error = ref("");

const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
const latestActivity = computed(() => data.value?.days.at(-1)?.activity_count_band ?? "0");

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    data.value = await getCommunityHeatmap(auth.accessToken, Number(windowDays.value));
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "数据热度加载失败";
  } finally {
    loading.value = false;
  }
}

function heatClass(band: string): string {
  if (band === "0") return "border-border bg-muted text-muted-foreground";
  if (band === "少于 10") return "border-primary/20 bg-primary/10 text-foreground";
  if (band === "10-49") return "border-primary/30 bg-primary/25 text-foreground";
  if (band === "50-99") return "border-primary/40 bg-primary/45 text-primary-foreground";
  if (band === "100-499") return "border-primary/60 bg-primary/65 text-primary-foreground";
  return "border-primary bg-primary text-primary-foreground";
}

function formatDay(day: string): string {
  const [, month, date] = day.split("-");
  return `${month}-${date}`;
}

function bandProgress(band: string): number {
  if (band === "0") return 0;
  if (band === "少于 10") return 20;
  if (band === "10-49") return 40;
  if (band === "50-99") return 60;
  if (band === "100-499") return 80;
  return 100;
}

function bandWidthClass(band: string): string {
  if (band === "0") return "w-0";
  if (band === "少于 10") return "w-1/5";
  if (band === "10-49") return "w-2/5";
  if (band === "50-99") return "w-3/5";
  if (band === "100-499") return "w-4/5";
  return "w-full";
}

onMounted(() => void load());
</script>

<template>
  <section class="mx-auto w-full max-w-6xl space-y-6">
    <header class="flex flex-col gap-4 rounded-2xl border bg-card p-6 shadow-sm sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <Badge>安全运营</Badge>
          <Badge variant="secondary"><ShieldCheck class="mr-1 size-3.5" />管理员聚合</Badge>
        </div>
        <h1 class="text-3xl font-semibold tracking-tight">数据热度图</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          按日期、星期和社区板块查看活动区间。服务端只返回聚合分桶，不包含 IP、地理位置、用户、哈希或单条内容。
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-sm text-muted-foreground">时间范围</span>
        <Select v-model="windowDays" @update:model-value="load">
          <SelectTrigger aria-label="数据热度时间范围" class="w-28"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">近 7 天</SelectItem>
            <SelectItem value="30">近 30 天</SelectItem>
            <SelectItem value="90">近 90 天</SelectItem>
          </SelectContent>
        </Select>
        <Button type="button" variant="outline" :disabled="loading" @click="load">
          <RefreshCw class="mr-2 size-4" :class="loading && 'animate-spin'" />刷新
        </Button>
      </div>
    </header>

    <p v-if="error" class="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>

    <div v-if="loading && !data" class="grid gap-4 md:grid-cols-2">
      <div v-for="index in 2" :key="index" class="h-64 animate-pulse rounded-2xl bg-muted" />
    </div>

    <template v-else-if="data">
      <section class="grid gap-4 sm:grid-cols-3" aria-label="热度统计摘要">
        <article class="rounded-xl border bg-card p-5">
          <p class="text-sm text-muted-foreground">最新日期活动区间</p>
          <p class="mt-3 text-3xl font-semibold">{{ latestActivity }}</p>
          <p class="mt-2 text-xs text-muted-foreground">不显示精确数量</p>
        </article>
        <article class="rounded-xl border bg-card p-5">
          <p class="text-sm text-muted-foreground">统计窗口</p>
          <p class="mt-3 text-3xl font-semibold">{{ data.window_days }} 天</p>
          <p class="mt-2 text-xs text-muted-foreground">固定日期桶</p>
        </article>
        <article class="rounded-xl border bg-card p-5">
          <p class="text-sm text-muted-foreground">活跃板块</p>
          <p class="mt-3 text-3xl font-semibold">{{ data.boards.length }}</p>
          <p class="mt-2 text-xs text-muted-foreground">仅统计当前启用板块</p>
        </article>
      </section>

      <section class="space-y-5 rounded-2xl border bg-card p-5 shadow-sm sm:p-6" aria-labelledby="daily-heatmap-heading">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div class="flex items-center gap-2 text-sm font-medium text-primary"><Activity class="size-4" />日期热度</div>
            <h2 id="daily-heatmap-heading" class="mt-2 text-xl font-semibold">社区活动分布</h2>
          </div>
          <div class="flex items-center gap-2 text-xs text-muted-foreground" aria-label="热度分桶图例">
            <span>低</span><span class="size-4 rounded-sm border bg-muted" /><span class="size-4 rounded-sm border border-primary/30 bg-primary/25" /><span class="size-4 rounded-sm border border-primary/60 bg-primary/65" /><span class="size-4 rounded-sm bg-primary" /><span>高</span>
          </div>
        </div>
        <div class="grid grid-cols-7 gap-2 text-center text-xs text-muted-foreground" aria-hidden="true">
          <span v-for="weekday in weekdays" :key="weekday">周{{ weekday }}</span>
        </div>
        <div class="grid grid-cols-7 gap-2">
          <div
            v-for="item in data.days"
            :key="item.day"
            class="flex aspect-square min-h-12 flex-col items-center justify-center rounded-md border p-1 text-center text-xs"
            :class="heatClass(item.activity_count_band)"
            :title="`${item.day}：活动 ${item.activity_count_band}，活跃板块 ${item.active_boards_count_band}`"
            :aria-label="`${item.day} 活动 ${item.activity_count_band}`"
          >
            <span class="font-mono">{{ formatDay(item.day) }}</span>
            <span class="mt-1 truncate text-[10px]">{{ item.activity_count_band }}</span>
          </div>
        </div>
      </section>

      <section class="space-y-5 rounded-2xl border bg-card p-5 shadow-sm sm:p-6" aria-labelledby="board-heatmap-heading">
        <div>
          <h2 id="board-heatmap-heading" class="text-xl font-semibold">板块热度</h2>
          <p class="mt-1 text-sm text-muted-foreground">按所选窗口汇总主题与回复活动，并进行隐私分桶。</p>
        </div>
        <div class="space-y-4">
          <div v-for="board in data.boards" :key="board.board_code" class="space-y-2">
            <div class="flex items-center justify-between gap-4 text-sm">
              <span class="font-medium">{{ board.board_name }}</span>
              <span class="text-muted-foreground">{{ board.activity_count_band }}</span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" :aria-valuenow="bandProgress(board.activity_count_band)" aria-valuemin="0" aria-valuemax="100" :aria-label="`${board.board_name} 活动区间 ${board.activity_count_band}`">
              <div class="h-full rounded-full bg-primary transition-all" :class="bandWidthClass(board.activity_count_band)" />
            </div>
          </div>
          <p v-if="data.boards.length === 0" class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">暂无可展示的启用板块。</p>
        </div>
      </section>
    </template>
  </section>
</template>
