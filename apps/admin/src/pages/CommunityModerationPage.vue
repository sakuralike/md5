<script setup lang="ts">
import type {
  AdminCommunityReportSummary,
  CommunityModerationAction,
  CommunityReportDecision,
  CommunityReportReason,
  CommunityReportStatus,
  AdminCommunityDirectMessageReportDetail,
  AdminCommunityDirectMessageReportSummary,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createCommunityModerationKey,
  listCommunityReports,
  moderateCommunityPost,
  resolveCommunityReport,
  getCommunityDirectMessageReport,
  listCommunityDirectMessageReports,
  resolveCommunityDirectMessageReport,
} from "../services/communityModeration";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const reports = ref<AdminCommunityReportSummary[]>([]);
const selected = ref<AdminCommunityReportSummary | null>(null);
const statusFilter = ref<CommunityReportStatus | "">("open");
const decision = ref<CommunityReportDecision>("dismiss");
const postAction = ref<CommunityModerationAction>("lock");
const note = ref("");
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const success = ref("");
const directReports = ref<AdminCommunityDirectMessageReportSummary[]>([]);
const selectedDirectReport = ref<AdminCommunityDirectMessageReportDetail | null>(null);
const directDecision = ref<"dismiss" | "remove_message">("dismiss");
const directNote = ref("");

const openCount = computed(() => reports.value.filter((item) => item.status === "open").length);

onMounted(() => {
  void loadReports();
  void loadDirectReports();
});

async function loadReports(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listCommunityReports(
      { status: statusFilter.value, page: 1, pageSize: 50 },
      auth.accessToken,
    );
    reports.value = response.items;
    if (selected.value) {
      selected.value = reports.value.find((item) => item.id === selected.value?.id) ?? null;
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "社区举报队列加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadDirectReports(): Promise<void> {
  try {
    const response = await listCommunityDirectMessageReports("open", auth.accessToken);
    directReports.value = response.items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "私信举报队列加载失败";
  }
}

async function selectDirectReport(report: AdminCommunityDirectMessageReportSummary): Promise<void> {
  try {
    selectedDirectReport.value = await getCommunityDirectMessageReport(report.id, auth.accessToken);
    directDecision.value = "dismiss";
    directNote.value = "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "私信举报详情加载失败";
  }
}

async function resolveDirectReport(): Promise<void> {
  const report = selectedDirectReport.value;
  if (!report || directNote.value.trim().length < 4 || busy.value) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const response = await resolveCommunityDirectMessageReport(
      report.id,
      { decision: directDecision.value, note: directNote.value.trim() },
      auth.accessToken,
      createCommunityModerationKey("direct-message-report"),
    );
    success.value = `私信举报已处理，审计记录 ${response.audit_id}`;
    selectedDirectReport.value = null;
    directNote.value = "";
    await loadDirectReports();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "私信举报处理失败";
  } finally {
    busy.value = false;
  }
}

function selectReport(report: AdminCommunityReportSummary): void {
  selected.value = report;
  decision.value = "dismiss";
  note.value = "";
  error.value = "";
  success.value = "";
}

async function resolveSelected(): Promise<void> {
  if (!selected.value || selected.value.status !== "open" || note.value.trim().length < 4) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const response = await resolveCommunityReport(
      selected.value.id,
      { decision: decision.value, note: note.value.trim() },
      auth.accessToken,
      createCommunityModerationKey("report"),
    );
    selected.value = response.report;
    success.value = `举报已处理，审计记录 ${response.audit_id}`;
    note.value = "";
    await loadReports();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "举报处理失败";
  } finally {
    busy.value = false;
  }
}

async function moderateSelectedPost(): Promise<void> {
  if (!selected.value || note.value.trim().length < 4) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const response = await moderateCommunityPost(
      selected.value.post_id,
      { action: postAction.value, note: note.value.trim() },
      auth.accessToken,
      createCommunityModerationKey("post"),
    );
    success.value = `主题状态已更新，审计记录 ${response.audit_id}`;
    note.value = "";
    await loadReports();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "主题治理操作失败";
  } finally {
    busy.value = false;
  }
}

function statusLabel(status: CommunityReportStatus): string {
  return { open: "待处理", resolved: "已处置", dismissed: "已驳回" }[status];
}

function reasonLabel(reason: CommunityReportReason): string {
  return {
    spam: "垃圾广告",
    harassment: "骚扰攻击",
    privacy: "隐私泄露",
    unsafe: "不安全内容",
    other: "其他问题",
  }[reason];
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}
</script>

<template>
  <section class="space-y-6">
    <header class="flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-sm lg:flex-row lg:items-end lg:justify-between">
      <div class="space-y-2">
        <div class="flex flex-wrap items-center gap-2">
          <Badge>社区治理</Badge>
          <Badge variant="secondary">待处理 {{ openCount }}</Badge>
        </div>
        <h1 class="text-2xl font-semibold tracking-tight">社区举报与主题审核</h1>
        <p class="text-sm text-muted-foreground">复核用户举报，移除违规内容，并对主题执行锁定、置顶、下架或恢复。</p>
      </div>
      <div class="flex flex-wrap items-end gap-3">
        <div class="space-y-2">
          <Label for="community-report-status">队列状态</Label>
          <Select v-model="statusFilter" @update:model-value="loadReports">
            <SelectTrigger id="community-report-status" class="w-40">
              <SelectValue placeholder="选择状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="open">待处理</SelectItem>
              <SelectItem value="resolved">已处置</SelectItem>
              <SelectItem value="dismissed">已驳回</SelectItem>
              <SelectItem value="">全部</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button type="button" variant="outline" :disabled="loading" @click="loadReports">
          {{ loading ? "加载中…" : "刷新" }}
        </Button>
      </div>
    </header>

    <p v-if="error" class="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{{ error }}</p>
    <p v-if="success" class="rounded-lg border bg-muted/50 p-3 text-sm">{{ success }}</p>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section class="space-y-3 rounded-xl border bg-card p-4 shadow-sm">
        <div class="flex items-center justify-between">
          <h2 class="font-semibold">举报队列</h2>
          <span class="text-sm text-muted-foreground">{{ reports.length }} 条</span>
        </div>
        <p v-if="!loading && reports.length === 0" class="rounded-lg bg-muted/40 p-6 text-center text-sm text-muted-foreground">
          当前筛选条件下没有社区举报。
        </p>
        <div class="space-y-2">
          <Button
            v-for="report in reports"
            :key="report.id"
            type="button"
            variant="ghost"
            class="h-auto w-full justify-start whitespace-normal border p-4 text-left"
            :class="selected?.id === report.id ? 'border-primary bg-accent' : ''"
            @click="selectReport(report)"
          >
            <span class="min-w-0 space-y-2">
              <span class="flex flex-wrap items-center gap-2">
                <Badge :variant="report.status === 'open' ? 'default' : 'secondary'">{{ statusLabel(report.status) }}</Badge>
                <Badge variant="outline">{{ reasonLabel(report.reason) }}</Badge>
                <span class="text-xs text-muted-foreground">{{ report.target_type === "post" ? "主题" : "回复" }}</span>
              </span>
              <strong class="block truncate">{{ report.post_title }}</strong>
              <span class="block line-clamp-2 text-sm font-normal text-muted-foreground">{{ report.target_excerpt }}</span>
              <span class="block text-xs font-normal text-muted-foreground">{{ report.reporter_username }} · {{ formatTime(report.created_at) }}</span>
            </span>
          </Button>
        </div>
      </section>

      <article v-if="selected" class="space-y-6 rounded-xl border bg-card p-5 shadow-sm">
        <div class="space-y-2">
          <div class="flex flex-wrap items-center gap-2">
            <Badge :variant="selected.status === 'open' ? 'default' : 'secondary'">{{ statusLabel(selected.status) }}</Badge>
            <Badge variant="outline">{{ reasonLabel(selected.reason) }}</Badge>
          </div>
          <h2 class="text-xl font-semibold">{{ selected.post_title }}</h2>
          <p class="text-sm text-muted-foreground">举报人 {{ selected.reporter_username }} · {{ formatTime(selected.created_at) }}</p>
        </div>

        <section class="space-y-2">
          <h3 class="font-medium">被举报内容</h3>
          <p class="whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-4 text-sm leading-6">{{ selected.target_excerpt }}</p>
        </section>
        <section class="space-y-2">
          <h3 class="font-medium">举报说明</h3>
          <p class="whitespace-pre-wrap break-words text-sm leading-6">{{ selected.details }}</p>
        </section>

        <section v-if="selected.status === 'open'" class="space-y-4 border-t pt-5">
          <h3 class="font-semibold">举报处置</h3>
          <div class="space-y-2">
            <Label for="community-report-decision">处理决定</Label>
            <Select v-model="decision">
              <SelectTrigger id="community-report-decision">
                <SelectValue placeholder="选择处理决定" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="dismiss">驳回举报</SelectItem>
                <SelectItem value="remove_content">移除被举报内容</SelectItem>
                <SelectItem value="remove_and_lock">移除内容并锁定主题</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label for="community-report-note">处理说明</Label>
            <Textarea id="community-report-note" v-model="note" placeholder="记录判断依据、内容风险和处置理由…" :maxlength="1000" />
          </div>
          <Button type="button" :disabled="busy || note.trim().length < 4" @click="resolveSelected">
            {{ busy ? "处理中…" : "确认处理举报" }}
          </Button>
        </section>
        <section v-else class="space-y-2 border-t pt-5 text-sm">
          <h3 class="font-semibold">处理结果</h3>
          <p>{{ selected.resolution_note || "未记录处理说明" }}</p>
          <p class="text-muted-foreground">{{ selected.resolved_by_username || "未知处理人" }} · {{ formatTime(selected.resolved_at) }}</p>
        </section>

        <section class="space-y-4 border-t pt-5">
          <h3 class="font-semibold">主题直接治理</h3>
          <div class="space-y-2">
            <Label for="community-post-action">治理动作</Label>
            <Select v-model="postAction">
              <SelectTrigger id="community-post-action">
                <SelectValue placeholder="选择治理动作" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="lock">锁定主题</SelectItem>
                <SelectItem value="unlock">解除锁定</SelectItem>
                <SelectItem value="pin">置顶主题</SelectItem>
                <SelectItem value="unpin">取消置顶</SelectItem>
                <SelectItem value="remove">下架主题</SelectItem>
                <SelectItem value="restore">恢复主题</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label for="community-post-note">治理说明</Label>
            <Textarea id="community-post-note" v-model="note" placeholder="记录治理动作的依据…" :maxlength="1000" />
          </div>
          <Button type="button" variant="outline" :disabled="busy || note.trim().length < 4" @click="moderateSelectedPost">
            {{ busy ? "处理中…" : "执行主题治理" }}
          </Button>
        </section>
      </article>
      <article v-else class="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
        请选择左侧举报查看详情并执行审核。
      </article>
    </div>

    <section class="space-y-4 rounded-xl border bg-card p-5 shadow-sm">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h2 class="font-semibold">私信举报队列</h2>
          <p class="text-sm text-muted-foreground">列表不展示正文；仅在 MFA 管理会话的具体案件详情中最小披露。</p>
        </div>
        <span class="text-sm text-muted-foreground">{{ directReports.length }} 条</span>
      </div>
      <div class="grid gap-4 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div class="space-y-2">
          <Button
            v-for="report in directReports"
            :key="report.id"
            type="button"
            variant="ghost"
            class="h-auto w-full justify-start whitespace-normal border p-3 text-left"
            @click="selectDirectReport(report)"
          >
            <span class="space-y-1">
              <span class="block text-xs text-muted-foreground">{{ report.reporter_username }} · {{ report.reason }}</span>
              <span class="block text-sm">{{ report.details }}</span>
            </span>
          </Button>
          <p v-if="directReports.length === 0" class="rounded-lg bg-muted/40 p-4 text-center text-sm text-muted-foreground">暂无待处理私信举报。</p>
        </div>
        <article v-if="selectedDirectReport" class="space-y-4 rounded-lg border p-4">
          <div>
            <h3 class="font-medium">受控消息案件详情</h3>
            <p class="text-sm text-muted-foreground">{{ selectedDirectReport.sender_username || "未知发送者" }} · {{ formatTime(selectedDirectReport.created_at) }}</p>
          </div>
          <p class="whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-3 text-sm">{{ selectedDirectReport.message_body || "消息已移除或不可读取" }}</p>
          <div class="space-y-2">
            <Label for="community-direct-message-report-decision">处理决定</Label>
            <Select v-model="directDecision">
              <SelectTrigger id="community-direct-message-report-decision"><SelectValue placeholder="选择处理决定" /></SelectTrigger>
              <SelectContent><SelectItem value="dismiss">驳回举报</SelectItem><SelectItem value="remove_message">移除消息</SelectItem></SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label for="community-direct-message-report-note">处理说明</Label>
            <Textarea id="community-direct-message-report-note" v-model="directNote" :maxlength="1000" placeholder="记录判断依据和处置理由…" />
          </div>
          <Button type="button" :disabled="busy || directNote.trim().length < 4" @click="resolveDirectReport">确认处理私信举报</Button>
        </article>
        <p v-else class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">请选择私信举报查看受控详情。</p>
      </div>
    </section>
  </section>
</template>
