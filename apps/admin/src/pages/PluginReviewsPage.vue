<script setup lang="ts">
import type { DesktopPluginCapability, DesktopPluginReport, DesktopPluginReviewDetail, DesktopPluginReviewMetrics, DesktopPluginReviewQueueItem } from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import PluginRunnerManagement from "../components/PluginRunnerManagement.vue";
import { approvePluginVersion, getPluginReview, getPluginReviewMetrics, listPluginReports, listPluginReviews, publishPluginVersion, rejectPluginVersion, resolvePluginReport, revokePluginVersion, rerunPluginStaticReview, yankPluginVersion } from "../services/pluginReviews";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const queue = ref<DesktopPluginReviewQueueItem[]>([]);
const reports = ref<DesktopPluginReport[]>([]);
const metrics = ref<DesktopPluginReviewMetrics | null>(null);
const selected = ref<DesktopPluginReviewDetail | null>(null);
const approvedCapabilities = ref<DesktopPluginCapability[]>([]);
const note = ref("按人工审核策略检查通过。");
const error = ref("");
const success = ref("");
const busy = ref(false);
const canApprove = computed(() => selected.value?.status === "manual_review_ready");

function statusLabel(status: string): string {
  return { review_queued: "等待自动审核", auto_review_running: "自动审核中", auto_review_failed: "自动审核未通过", manual_review_ready: "待人工审核", approved: "已批准", published: "已发布", rejected: "已驳回", yanked: "已下架", revoked: "已撤销" }[status] ?? status;
}

async function load(): Promise<void> {
  error.value = "";
  try {
    const [reviews, reportList, metricSnapshot] = await Promise.all([listPluginReviews(auth.accessToken), listPluginReports(auth.accessToken), getPluginReviewMetrics(auth.accessToken)]);
    queue.value = reviews.items;
    reports.value = reportList.items;
    metrics.value = metricSnapshot;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法加载插件审核工作台";
  }
}

async function selectReview(item: DesktopPluginReviewQueueItem): Promise<void> {
  selected.value = await getPluginReview(auth.accessToken, item.version_id);
  approvedCapabilities.value = [...selected.value.requested_capabilities];
}

function toggleCapability(capability: DesktopPluginCapability, checked: boolean | "indeterminate"): void {
  approvedCapabilities.value = checked === true
    ? [...new Set([...approvedCapabilities.value, capability])]
    : approvedCapabilities.value.filter((item) => item !== capability);
}

async function run(action: "approve" | "reject" | "publish" | "yank" | "revoke"): Promise<void> {
  if (!selected.value) return;
  busy.value = true;
  error.value = "";
  try {
    const current = selected.value;
    selected.value = action === "approve"
      ? await approvePluginVersion(auth.accessToken, current, approvedCapabilities.value, note.value)
      : action === "reject"
        ? await rejectPluginVersion(auth.accessToken, current, note.value)
        : action === "publish"
          ? await publishPluginVersion(auth.accessToken, current)
          : action === "yank"
            ? await yankPluginVersion(auth.accessToken, current, note.value)
            : await revokePluginVersion(auth.accessToken, current, note.value);
    success.value = "插件审核状态已更新。";
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "插件审核操作失败";
  } finally {
    busy.value = false;
  }
}

async function resolveReport(report: DesktopPluginReport): Promise<void> {
  busy.value = true;
  try {
    await resolvePluginReport(auth.accessToken, report, note.value);
    success.value = "举报已处置。";
    await load();
  } finally {
    busy.value = false;
  }
}

async function rerun(): Promise<void> {
  if (!selected.value) return;
  busy.value = true;
  try {
    selected.value = await rerunPluginStaticReview(auth.accessToken, selected.value);
    success.value = "已重新排队自动审核。";
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "重新执行自动审核失败";
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="space-y-6 pt-16 lg:pt-0">
    <Button v-if="selected && ['auto_review_failed','review_queued'].includes(selected.status)" size="sm" variant="outline" :disabled="busy" @click="rerun">重新执行自动审核</Button>
    <header class="space-y-2"><p class="text-xs font-semibold text-primary">PLUGIN REVIEW</p><h1 class="text-3xl font-semibold">插件审核工作台</h1><p class="text-sm text-muted-foreground">审核权限差异、签名摘要、版本历史、发布状态与用户举报。</p></header>
    <div v-if="error" class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive"><strong class="block">操作未完成</strong><p class="mt-1">{{ error }}</p></div>
    <div v-if="success" class="rounded-md border border-primary/40 bg-primary/10 p-4 text-sm"><strong class="block">操作成功</strong><p class="mt-1 text-muted-foreground">{{ success }}</p></div>
    <div class="grid gap-6 xl:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.4fr)]">
      <Card><CardHeader><CardTitle>审核队列</CardTitle><CardDescription>选择版本查看完整审核事实。</CardDescription></CardHeader><CardContent class="space-y-3"><Button v-for="item in queue" :key="item.version_id" variant="outline" class="h-auto w-full justify-between p-4 text-left" @click="selectReview(item)"><span><strong class="block">{{ item.plugin_name }} {{ item.semver }}</strong><small class="text-muted-foreground">{{ item.plugin_slug }}</small></span><Badge>{{ statusLabel(item.status) }}</Badge></Button><p v-if="queue.length === 0" class="text-sm text-muted-foreground">暂无待审核插件版本。</p></CardContent></Card>
      <Card><CardHeader><CardTitle>版本审核详情</CardTitle><CardDescription>批准权限必须是开发者申请权限的子集。</CardDescription></CardHeader><CardContent v-if="selected" class="space-y-5"><div class="flex flex-wrap gap-2"><Badge>{{ statusLabel(selected.status) }}</Badge><Badge variant="outline">{{ selected.semver }}</Badge><Badge variant="outline">{{ selected.risk_tier }}</Badge></div><p class="break-all text-xs text-muted-foreground">Manifest SHA-256：{{ selected.manifest_sha256 }}</p><div class="space-y-3 border-y py-4"><h3 class="font-medium">自动静态与供应链审核</h3><div v-for="runItem in selected.review_runs" :key="runItem.id" class="space-y-3 rounded-md border p-3"><div class="flex flex-wrap items-center gap-2"><Badge>{{ runItem.status }}</Badge><code class="text-xs">{{ runItem.policy_version }}</code><span class="text-xs text-muted-foreground">第 {{ runItem.attempt }} 次执行</span></div><p v-if="runItem.error_message" class="text-sm text-destructive">{{ runItem.error_message }}</p><div v-for="finding in runItem.findings" :key="finding.id" class="rounded-md bg-muted p-3 text-sm"><div class="flex flex-wrap items-center gap-2"><code>{{ finding.rule_id }}</code><Badge variant="outline">{{ finding.stage }}</Badge><Badge :variant="finding.blocked ? 'destructive' : 'secondary'">{{ finding.severity }}</Badge></div><strong class="mt-2 block">{{ finding.title }}</strong><p class="text-muted-foreground">{{ finding.detail }}</p><code v-if="finding.file_path" class="mt-1 block break-all text-xs">{{ finding.file_path }}</code></div></div><p v-if="selected.review_runs.length === 0" class="text-sm text-muted-foreground">自动审核尚未开始。</p></div><fieldset class="space-y-3"><legend class="text-sm font-medium">批准权限</legend><div v-for="capability in selected.requested_capabilities" :key="capability" class="flex items-center gap-3"><Checkbox :id="`plugin-capability-${capability}`" :checked="approvedCapabilities.includes(capability)" @update:checked="toggleCapability(capability, $event)" /><Label :for="`plugin-capability-${capability}`"><code>{{ capability }}</code></Label></div></fieldset><div class="space-y-2"><Label for="plugin-review-note">审核意见或处置原因</Label><Textarea id="plugin-review-note" v-model="note" rows="3" /></div><div class="flex flex-wrap gap-2"><Button v-if="canApprove" :disabled="busy" @click="run('approve')">批准权限</Button><Button v-if="canApprove" variant="destructive" :disabled="busy" @click="run('reject')">驳回</Button><Button v-if="selected.status === 'approved'" :disabled="busy" @click="run('publish')">发布 stable</Button><Button v-if="selected.status === 'published'" variant="outline" :disabled="busy" @click="run('yank')">普通下架</Button><Button v-if="['approved','published','yanked'].includes(selected.status)" variant="destructive" :disabled="busy" @click="run('revoke')">紧急撤销</Button></div><div class="space-y-2 border-t pt-4"><h3 class="font-medium">不可变审核历史</h3><div v-for="event in selected.events" :key="event.id" class="rounded-md bg-muted p-3 text-sm"><strong>{{ statusLabel(event.kind) }}</strong><p v-if="event.note" class="text-muted-foreground">{{ event.note }}</p></div></div></CardContent><CardContent v-else class="text-sm text-muted-foreground">从审核队列选择一个版本。</CardContent></Card>
    </div>
    <Card><CardHeader><CardTitle>用户举报</CardTitle><CardDescription>举报不自动下架；审核员需结合证据决定处置。</CardDescription></CardHeader><CardContent class="space-y-3"><article v-for="report in reports" :key="report.id" class="flex flex-col gap-3 rounded-md border p-4 sm:flex-row sm:items-center sm:justify-between"><div><div class="flex gap-2"><Badge variant="outline">{{ report.category }}</Badge><Badge>{{ report.status }}</Badge></div><p class="mt-2 text-sm">{{ report.description }}</p></div><Button v-if="report.status !== 'resolved'" variant="outline" :disabled="busy" @click="resolveReport(report)">标记已处置</Button></article><p v-if="reports.length === 0" class="text-sm text-muted-foreground">暂无插件举报。</p></CardContent></Card>
    <Card v-if="selected"><CardHeader><CardTitle>动态执行时间线</CardTitle><CardDescription>显示每个 Windows Runner 任务的证据完整性和销毁证明。</CardDescription></CardHeader><CardContent class="space-y-3"><template v-for="runItem in selected.review_runs" :key="`timeline-${runItem.id}`"><article v-for="task in runItem.dynamic_tasks" :key="task.id" class="rounded-md border border-dashed p-3 text-sm"><div class="flex flex-wrap items-center gap-2"><Badge variant="outline">{{ task.architecture }}</Badge><Badge :variant="task.status === 'passed' ? 'secondary' : task.status === 'blocked' ? 'destructive' : 'outline'">{{ task.status }}</Badge><span class="text-xs text-muted-foreground">第 {{ task.attempt }} 次</span></div><p class="mt-2 text-xs text-muted-foreground">证据 {{ task.evidence_complete ? '完整' : '不完整' }} · 新环境 {{ task.fresh_environment ? '是' : '否' }} · 销毁证明 {{ task.destruction_proof_sha256 || '无' }}</p><p v-if="task.error_message" class="text-xs text-destructive">{{ task.error_message }}</p></article></template><p v-if="selected.review_runs.every((runItem) => runItem.dynamic_tasks.length === 0)" class="text-sm text-muted-foreground">尚未生成动态 Runner 任务。</p></CardContent></Card>
    <PluginRunnerManagement />
    <Card v-if="metrics"><CardHeader><CardTitle>审核运行指标</CardTitle><CardDescription>积压、Runner 容量和最近完成情况。</CardDescription></CardHeader><CardContent class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><div class="rounded-md border p-3"><p class="text-xs text-muted-foreground">待处理积压</p><p class="mt-1 text-xl font-semibold">{{ Object.values(metrics.queue_depth_by_architecture).reduce((sum, value) => sum + value, 0) }}</p></div><div class="rounded-md border p-3"><p class="text-xs text-muted-foreground">可用 Runner</p><p class="mt-1 text-xl font-semibold">{{ Object.values(metrics.runner_capacity_by_architecture).reduce((sum, value) => sum + value, 0) }}</p></div><div class="rounded-md border p-3"><p class="text-xs text-muted-foreground">最长等待</p><p class="mt-1 text-xl font-semibold">{{ metrics.oldest_queued_seconds === null ? "无" : `${Math.round(metrics.oldest_queued_seconds)} 秒` }}</p></div><div class="rounded-md border p-3"><p class="text-xs text-muted-foreground">近 24 小时完成</p><p class="mt-1 text-xl font-semibold">{{ metrics.completed_last_24_hours }}</p></div><p class="text-xs text-muted-foreground sm:col-span-2 xl:col-span-4">平均审核 {{ metrics.average_review_seconds === null ? "无" : `${Math.round(metrics.average_review_seconds)} 秒` }} · P95 {{ metrics.p95_review_seconds === null ? "无" : `${Math.round(metrics.p95_review_seconds)} 秒` }} · 安装事件 {{ metrics.install_events_last_24_hours }}</p></CardContent></Card>
  </section>
</template>
