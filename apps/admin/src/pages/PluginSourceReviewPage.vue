<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getPluginReviewSource, reviewPluginSourceWithLlm } from "../services/pluginReviews";
import { useAdminAuthStore } from "../stores/auth";

const route = useRoute();
const auth = useAdminAuthStore();
const files = ref<Array<{ path: string; content: string; truncated: boolean }>>([]);
const result = ref<{ verdict: string; risk_level: string; summary: string } | null>(null);
const error = ref("");
const busy = ref(false);
const versionId = String(route.params.versionId);

async function load(): Promise<void> {
  try {
    files.value = (await getPluginReviewSource(auth.accessToken, versionId)).files;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "源码加载失败";
  }
}

async function runLlmReview(): Promise<void> {
  busy.value = true;
  error.value = "";
  try {
    result.value = await reviewPluginSourceWithLlm(auth.accessToken, versionId);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "大模型源码审查失败";
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="space-y-6 pt-16 lg:pt-0">
    <header class="space-y-2"><h1 class="text-3xl font-semibold">插件源码审查</h1><p class="text-sm text-muted-foreground">仅展示插件包中显式提交的文本源码。</p></header>
    <div v-if="error" class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">{{ error }}</div>
    <Card><CardHeader class="flex flex-row items-center justify-between gap-3"><CardTitle>源码文件</CardTitle><Button :disabled="busy || files.length === 0" @click="runLlmReview">调用大模型审查</Button></CardHeader><CardContent class="space-y-4"><article v-for="file in files" :key="file.path" class="space-y-2 rounded-md border p-3"><code class="block text-xs">{{ file.path }}</code><pre class="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded bg-muted p-3 text-xs">{{ file.content }}</pre><p v-if="file.truncated" class="text-xs text-muted-foreground">文件已截断显示。</p></article><p v-if="files.length === 0" class="text-sm text-muted-foreground">该版本未提交可审源码。</p></CardContent></Card>
    <Card v-if="result"><CardHeader><CardTitle>大模型审查结果</CardTitle></CardHeader><CardContent class="space-y-2 text-sm"><p>结论：{{ result.verdict }} · 风险：{{ result.risk_level }}</p><p class="text-muted-foreground">{{ result.summary }}</p></CardContent></Card>
  </section>
</template>
