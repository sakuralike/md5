<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { getPluginReviewSource, reviewPluginSourceWithLlm } from "../services/pluginReviews";
import { useAdminAuthStore } from "../stores/auth";

const route = useRoute();
const auth = useAdminAuthStore();
const files = ref<Array<{ path: string; content: string; truncated: boolean }>>([]);
const result = ref<{ verdict: string; risk_level: string; summary: string } | null>(null);
const error = ref("");
const busy = ref(false);
const prompt = ref("");
const runtimeInfo = ref("尚未调用大模型。\n等待管理员提交审查请求。\n");
const presets = ["请分析源码中的恶意行为", "请分析数据外传和权限滥用风险", "请检查命令执行、持久化和隐蔽通信", "请评估源码是否符合插件申请权限"];
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
    runtimeInfo.value = `请求时间：${new Date().toISOString()}\n源码文件数：${files.value.length}\n审查请求：${prompt.value || "请分析源码中的恶意行为、数据外传和权限滥用风险。"}\n`;
    result.value = await reviewPluginSourceWithLlm(auth.accessToken, versionId, prompt.value || presets[0]);
    runtimeInfo.value += `完成时间：${new Date().toISOString()}\n结论：${result.value.verdict}\n风险级别：${result.value.risk_level}\n`;
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
    <Card><CardHeader><CardTitle>源码文件</CardTitle></CardHeader><CardContent class="space-y-4"><article v-for="file in files" :key="file.path" class="space-y-2 rounded-md border p-3"><code class="block text-xs">{{ file.path }}</code><pre class="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded bg-muted p-3 text-xs">{{ file.content }}</pre><p v-if="file.truncated" class="text-xs text-muted-foreground">文件已截断显示。</p></article><p v-if="files.length === 0" class="text-sm text-muted-foreground">该版本未提交可审源码。</p></CardContent></Card>
    <Card><CardHeader><CardTitle>大模型审查请求</CardTitle></CardHeader><CardContent class="space-y-3"><div class="flex flex-wrap gap-2"><Button v-for="preset in presets" :key="preset" type="button" size="sm" variant="outline" @click="prompt = preset">{{ preset }}</Button></div><Textarea v-model="prompt" rows="3" placeholder="请输入自然语言审查要求" /><Button :disabled="busy || files.length === 0" @click="runLlmReview">调用大模型审查</Button><pre class="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-3 text-xs">{{ runtimeInfo }}</pre></CardContent></Card>
    <Card v-if="result"><CardHeader><CardTitle>大模型审查结果</CardTitle></CardHeader><CardContent class="space-y-2 text-sm"><p>结论：{{ result.verdict }} · 风险：{{ result.risk_level }}</p><p class="text-muted-foreground">{{ result.summary }}</p></CardContent></Card>
  </section>
</template>
