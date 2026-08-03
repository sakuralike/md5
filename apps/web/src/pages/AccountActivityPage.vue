<script setup lang="ts">
import type { RevealHistoryItem } from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { listRevealHistory } from "../services/account";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const items = ref<RevealHistoryItem[]>([]);
const total = ref(0);
const busy = ref(false);
const error = ref("");

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

async function load(): Promise<void> {
  busy.value = true;
  error.value = "";
  try {
    const response = await listRevealHistory(auth.accessToken);
    items.value = response.items;
    total.value = response.total;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载揭示历史";
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="mx-auto max-w-6xl space-y-6">
    <div class="space-y-2">
      <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Account activity</p>
      <h1 class="text-3xl font-semibold tracking-tight text-foreground">账号活动记录</h1>
      <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
        仅展示档案指纹摘要、揭示时间、结果状态与审计引用，不保存或回放历史明文密码。
      </p>
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>加载失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Card>
      <CardHeader class="flex flex-row items-start justify-between gap-4">
        <div class="space-y-1">
          <CardTitle>密码揭示历史</CardTitle>
          <CardDescription>共 {{ total }} 条受审计记录。</CardDescription>
        </div>
        <Button variant="outline" :disabled="busy" @click="load">
          {{ busy ? "刷新中…" : "刷新" }}
        </Button>
      </CardHeader>
      <CardContent class="space-y-3">
        <div
          v-for="item in items"
          :key="item.audit_id"
          class="rounded-xl border border-border/70 bg-background/55 p-4 backdrop-blur"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="font-medium text-foreground">{{ formatDate(item.revealed_at) }}</p>
              <p class="mt-1 text-xs text-muted-foreground">审计引用：{{ item.audit_id }}</p>
            </div>
            <Badge :variant="item.result === 'success' ? 'default' : 'destructive'">
              {{ item.result === "success" ? "成功" : item.result }}
            </Badge>
          </div>
          <div class="mt-4 flex flex-wrap gap-2">
            <Badge
              v-for="fingerprint in item.fingerprint_summary"
              :key="fingerprint"
              variant="secondary"
              class="font-mono font-normal"
            >
              {{ fingerprint }}
            </Badge>
            <span v-if="item.fingerprint_summary.length === 0" class="text-sm text-muted-foreground">
              当前档案指纹已不可用
            </span>
          </div>
        </div>
        <div
          v-if="!busy && items.length === 0"
          class="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground"
        >
          暂无密码揭示记录。
        </div>
      </CardContent>
    </Card>
  </section>
</template>
