<script setup lang="ts">
import type { DesktopPluginReviewPolicy, DesktopPluginRunner } from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { createPluginRunner, getPluginReviewPolicy, listPluginRunners, revokePluginRunner, savePluginReviewLlmKey, savePluginReviewPolicy, testPluginReviewLlm } from "../services/pluginReviews";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const runners = ref<DesktopPluginRunner[]>([]);
const policy = ref<DesktopPluginReviewPolicy | null>(null);
const name = ref("");
const architecture = ref<"windows-x64" | "windows-arm64">("windows-x64");
const certificateFingerprint = ref("");
const registrationSecret = ref("");
const llmApiKey = ref("");
const llmConnection = ref("");
const error = ref("");
const busy = ref(false);
const saved = ref("");

async function load(): Promise<void> {
  try {
    const [runnerList, currentPolicy] = await Promise.all([
      listPluginRunners(auth.accessToken),
      getPluginReviewPolicy(auth.accessToken),
    ]);
    runners.value = runnerList.items;
    policy.value = currentPolicy;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载 Windows Runner";
  }
}

async function savePolicy(): Promise<void> {
  if (!policy.value) return;
  busy.value = true;
  error.value = "";
  try {
    policy.value = await savePluginReviewPolicy(auth.accessToken, policy.value);
    saved.value = "审核策略已保存";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "审核策略保存失败";
  } finally {
    busy.value = false;
  }
}

async function saveLlmConfig(): Promise<void> {
  if (!policy.value) return;
  busy.value = true;
  error.value = "";
  saved.value = "";
  try {
    policy.value = await savePluginReviewPolicy(auth.accessToken, policy.value);
    if (llmApiKey.value.trim()) {
      await savePluginReviewLlmKey(auth.accessToken, llmApiKey.value.trim());
      llmApiKey.value = "";
    }
    await load();
    saved.value = "大模型配置已保存";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "大模型配置保存失败";
  } finally {
    busy.value = false;
  }
}

function updateDynamicReview(checked: boolean | "indeterminate"): void {
  if (policy.value) policy.value.dynamic_review_enabled = checked === true;
}

function updateLlmReview(checked: boolean | "indeterminate"): void {
  if (policy.value) policy.value.llm_review_enabled = checked === true;
}

async function saveLlmKey(): Promise<void> {
  if (!llmApiKey.value) return;
  busy.value = true;
  error.value = "";
  try {
    await savePluginReviewLlmKey(auth.accessToken, llmApiKey.value);
    llmApiKey.value = "";
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "保存模型 Key 失败";
  } finally {
    busy.value = false;
  }
}

async function testLlmConnection(): Promise<void> {
  busy.value = true;
  error.value = "";
  llmConnection.value = "";
  try {
    const result = await testPluginReviewLlm(auth.accessToken);
    llmConnection.value = `${result.provider} · ${result.model}`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "大模型连接测试失败";
  } finally {
    busy.value = false;
  }
}

async function createRunner(): Promise<void> {
  busy.value = true;
  error.value = "";
  registrationSecret.value = "";
  try {
    const runner = await createPluginRunner(auth.accessToken, {
      name: name.value,
      architecture: architecture.value,
      certificate_fingerprint: certificateFingerprint.value,
    });
    registrationSecret.value = runner.runner_secret ?? "";
    name.value = "";
    certificateFingerprint.value = "";
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Runner 登记失败";
  } finally {
    busy.value = false;
  }
}

async function revoke(runner: DesktopPluginRunner): Promise<void> {
  busy.value = true;
  try {
    await revokePluginRunner(auth.accessToken, runner);
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Runner 撤销失败";
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-5">
  <Card v-if="policy">
    <CardHeader>
      <CardTitle>大模型审核配置</CardTitle>
      <CardDescription>模型 Key 仅加密保存在服务器，不会回显到管理端。</CardDescription>
    </CardHeader>
    <CardContent class="space-y-4">
      <div class="flex items-center gap-3"><Checkbox id="policy-llm-review" :checked="policy.llm_review_enabled" @update:checked="updateLlmReview" /><Label for="policy-llm-review">启用大模型二次审核</Label></div>
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div class="space-y-2"><Label for="policy-llm-provider">模型协议</Label><Select v-model="policy.llm_provider"><SelectTrigger id="policy-llm-provider"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="disabled">未配置</SelectItem><SelectItem value="openai_compatible">OpenAI 兼容</SelectItem><SelectItem value="anthropic_compatible">Anthropic 兼容</SelectItem></SelectContent></Select></div>
        <div class="space-y-2"><Label for="policy-llm-url">API 地址</Label><Input id="policy-llm-url" v-model="policy.llm_base_url" placeholder="https://api.deepseek.com" /></div>
        <div class="space-y-2"><Label for="policy-llm-model">模型名称</Label><Input id="policy-llm-model" v-model="policy.llm_model" placeholder="deepseek-chat" /></div>
        <div class="space-y-2"><Label for="policy-llm-timeout">模型超时（秒）</Label><Input id="policy-llm-timeout" v-model.number="policy.llm_timeout_seconds" type="number" min="5" max="120" /></div>
      </div>
      <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end">
        <div class="space-y-2"><Label for="policy-llm-key">模型 API Key</Label><Input id="policy-llm-key" v-model="llmApiKey" type="password" autocomplete="off" :placeholder="policy.llm_api_key_configured ? '已配置，填写以替换' : '填写模型 API Key'" /></div>
        <Button variant="outline" :disabled="busy || !llmApiKey" @click="saveLlmKey">保存模型 Key</Button>
        <Button variant="outline" :disabled="busy || !policy.llm_api_key_configured" @click="testLlmConnection">测试模型连接</Button>
      </div>
      <p v-if="llmConnection" class="text-xs text-muted-foreground">连接成功：{{ llmConnection }}</p>
      <Button :disabled="busy" @click="saveLlmConfig">保存大模型配置</Button>
      <p v-if="saved" class="text-xs text-muted-foreground">{{ saved }}</p>
    </CardContent>
  </Card>
  <Card>
    <CardHeader>
      <CardTitle>Windows 动态审核执行器</CardTitle>
      <CardDescription>Runner 使用 mTLS、专用凭据和短期单任务 Token；不持有生产数据库或对象存储凭据。</CardDescription>
    </CardHeader>
    <CardContent class="space-y-5">
      <div v-if="error" class="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"><strong>操作未完成</strong><p class="mt-1">{{ error }}</p></div>
      <div v-if="registrationSecret" class="rounded-md border border-primary/40 bg-primary/10 p-3 text-sm"><strong>一次性 Runner Secret</strong><code class="mt-1 block break-all">{{ registrationSecret }}</code></div>
      <section v-if="policy" class="space-y-3 border-b pb-5">
        <div><h3 class="font-medium">审核运行策略</h3><p class="text-xs text-muted-foreground">{{ policy.policy_version }} · 静态引擎 {{ policy.static_engine_version }} · 动态引擎 {{ policy.dynamic_engine_version }}</p></div>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div class="space-y-2"><Label for="policy-static-lease">静态租约（秒）</Label><Input id="policy-static-lease" v-model.number="policy.static_lease_seconds" type="number" min="60" max="1800" /></div>
          <div class="space-y-2"><Label for="policy-dynamic-lease">动态租约（秒）</Label><Input id="policy-dynamic-lease" v-model.number="policy.dynamic_lease_seconds" type="number" min="60" max="1800" /></div>
          <div class="space-y-2"><Label for="policy-task-token">任务 Token（秒）</Label><Input id="policy-task-token" v-model.number="policy.task_token_seconds" type="number" min="60" max="3600" /></div>
          <div class="space-y-2"><Label for="policy-runner-offline">Runner 失联（秒）</Label><Input id="policy-runner-offline" v-model.number="policy.runner_offline_seconds" type="number" min="30" max="600" /></div>
          <div class="space-y-2"><Label for="policy-static-attempts">静态重试上限</Label><Input id="policy-static-attempts" v-model.number="policy.maximum_static_attempts" type="number" min="1" max="5" /></div>
          <div class="space-y-2"><Label for="policy-dynamic-attempts">动态重试上限</Label><Input id="policy-dynamic-attempts" v-model.number="policy.maximum_dynamic_attempts" type="number" min="1" max="5" /></div>
          <div class="space-y-2"><Label for="policy-revocation-refresh">撤销刷新（小时）</Label><Input id="policy-revocation-refresh" v-model.number="policy.revocation_refresh_hours" type="number" min="1" max="24" /></div>
          <div class="space-y-2"><Label for="policy-revocation-stale">离线过期（小时）</Label><Input id="policy-revocation-stale" v-model.number="policy.revocation_max_stale_hours" type="number" min="24" max="720" /></div>
        </div>
        <div class="flex items-center gap-3"><Checkbox id="policy-dynamic-review" :checked="policy.dynamic_review_enabled" @update:checked="updateDynamicReview" /><Label for="policy-dynamic-review">启用 Windows 动态审核</Label></div>
        <Button :disabled="busy" @click="savePolicy">保存审核策略</Button>
      </section>
      <div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_13rem_minmax(0,1.4fr)_auto] lg:items-end">
        <div class="space-y-2"><Label for="runner-name">Runner 名称</Label><Input id="runner-name" v-model="name" /></div>
        <div class="space-y-2"><Label for="runner-architecture">架构</Label><Select v-model="architecture"><SelectTrigger id="runner-architecture"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="windows-x64">windows-x64</SelectItem><SelectItem value="windows-arm64">windows-arm64</SelectItem></SelectContent></Select></div>
        <div class="space-y-2"><Label for="runner-certificate">客户端证书 SHA-256</Label><Input id="runner-certificate" v-model="certificateFingerprint" class="font-mono" /></div>
        <Button :disabled="busy" @click="createRunner">登记 Runner</Button>
      </div>
      <div class="space-y-3">
        <article v-for="runner in runners" :key="runner.id" class="grid gap-3 rounded-md border p-4 md:grid-cols-[minmax(0,1fr)_auto]">
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2"><strong>{{ runner.name }}</strong><Badge>{{ runner.status }}</Badge><Badge variant="outline">{{ runner.architecture }}</Badge></div>
            <p class="break-all font-mono text-xs text-muted-foreground">证书 {{ runner.certificate_fingerprint }}</p>
            <p class="text-xs text-muted-foreground">策略 {{ runner.policy_version || "未上报" }} · 探针 {{ runner.probe_version || "未上报" }}</p>
            <p class="break-all text-xs text-muted-foreground">镜像 {{ runner.image_digest || "未上报" }}</p>
            <p class="text-xs text-muted-foreground">最后心跳 {{ runner.last_heartbeat_at || "尚未连接" }}</p>
          </div>
          <Button v-if="runner.status !== 'revoked'" variant="destructive" size="sm" :disabled="busy" @click="revoke(runner)">撤销</Button>
        </article>
        <p v-if="runners.length === 0" class="text-sm text-muted-foreground">尚未登记 Windows Runner。</p>
      </div>
    </CardContent>
  </Card>
  </div>
</template>
