<script setup lang="ts">
import {
  ApiError,
  type AdminAuditLogEntry,
} from "@password-detective/api-contract";
import { Download, Eye, FileSearch2, RefreshCw, Search, ShieldCheck } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  downloadAdminAuditLogs,
  getAdminAuditLog,
  listAdminAuditLogs,
  type AdminAuditLogFilters,
} from "../services/auditLogs";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const items = ref<AdminAuditLogEntry[]>([]);
const selected = ref<AdminAuditLogEntry | null>(null);
const detailOpen = ref(false);
const loading = ref(false);
const detailLoading = ref(false);
const exporting = ref(false);
const error = ref("");
const message = ref("");
const page = ref(1);
const pageSize = 20;
const total = ref(0);

const queryFilter = ref("");
const actionFilter = ref("");
const targetTypeFilter = ref("");
const resultFilter = ref("all");
const createdFromFilter = ref("");
const createdToFilter = ref("");

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const rangeLabel = computed(() => {
  if (total.value === 0) return "暂无记录";
  const start = (page.value - 1) * pageSize + 1;
  const end = Math.min(page.value * pageSize, total.value);
  return `第 ${start}–${end} 条，共 ${total.value} 条`;
});

function describeError(value: unknown): string {
  if (value instanceof ApiError) return value.body.message;
  return value instanceof Error ? value.message : "审计服务暂时不可用";
}

function toIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

function currentFilters(includePagination = true): AdminAuditLogFilters {
  return {
    action: actionFilter.value || undefined,
    result: resultFilter.value === "all" ? undefined : resultFilter.value,
    targetType: targetTypeFilter.value || undefined,
    query: queryFilter.value || undefined,
    createdFrom: toIso(createdFromFilter.value),
    createdTo: toIso(createdToFilter.value),
    ...(includePagination ? { page: page.value, pageSize } : {}),
  };
}

async function loadLogs(): Promise<void> {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    const response = await listAdminAuditLogs(currentFilters(), auth.accessToken);
    items.value = response.items;
    total.value = response.total;
    if (page.value > totalPages.value) {
      page.value = totalPages.value;
      await loadLogs();
    }
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function applyFilters(): Promise<void> {
  page.value = 1;
  await loadLogs();
}

async function resetFilters(): Promise<void> {
  queryFilter.value = "";
  actionFilter.value = "";
  targetTypeFilter.value = "";
  resultFilter.value = "all";
  createdFromFilter.value = "";
  createdToFilter.value = "";
  page.value = 1;
  await loadLogs();
}

async function changePage(nextPage: number): Promise<void> {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value);
  await loadLogs();
}

async function openDetail(item: AdminAuditLogEntry): Promise<void> {
  selected.value = item;
  detailOpen.value = true;
  detailLoading.value = true;
  error.value = "";
  try {
    selected.value = await getAdminAuditLog(item.id, auth.accessToken);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    detailLoading.value = false;
  }
}

async function exportCsv(): Promise<void> {
  exporting.value = true;
  error.value = "";
  message.value = "";
  try {
    const download = await downloadAdminAuditLogs(currentFilters(false), auth.accessToken);
    const url = URL.createObjectURL(download.blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = download.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    message.value = `已导出 ${download.rowCount} 条脱敏审计记录。`;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    exporting.value = false;
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function resultVariant(result: string): "secondary" | "destructive" | "outline" {
  if (result === "success") return "secondary";
  if (result === "failure") return "destructive";
  return "outline";
}

function resultLabel(result: string): string {
  const labels: Record<string, string> = {
    success: "成功",
    failure: "失败",
    blocked: "阻止",
  };
  return labels[result] ?? result;
}

function roleLabel(role: AdminAuditLogEntry["actor_role"]): string {
  if (!role) return "系统/匿名";
  return {
    user: "用户",
    trusted_contributor: "可信贡献者",
    moderator: "审核员",
    admin: "管理员",
    service: "服务账号",
  }[role];
}

onMounted(loadLogs);
</script>

<template>
  <section class="space-y-6">
    <header class="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/80 p-6 shadow-sm shadow-slate-200/70 backdrop-blur-xl md:flex-row md:items-end md:justify-between">
      <div>
        <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-sky-700">
          <ShieldCheck class="h-4 w-4" aria-hidden="true" />
          N2 Governance Workbench
        </div>
        <h1 class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">全局系统日志（审计日志）</h1>
        <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          查询已落库的真实业务审计事件，查看脱敏详情，并按当前筛选条件导出受限 CSV。
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button variant="outline" :disabled="loading" @click="loadLogs">
          <RefreshCw :class="['h-4 w-4', loading ? 'animate-spin' : '']" aria-hidden="true" />
          刷新
        </Button>
        <Button :disabled="exporting || loading" @click="exportCsv">
          <Download class="h-4 w-4" aria-hidden="true" />
          {{ exporting ? "导出中" : "导出 CSV" }}
        </Button>
      </div>
    </header>

    <div v-if="error" class="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
      {{ error }}
    </div>
    <div v-if="message" class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" aria-live="polite">
      {{ message }}
    </div>

    <section class="rounded-3xl border border-white/70 bg-white/80 p-5 shadow-sm shadow-slate-200/70 backdrop-blur-xl">
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div class="space-y-2 md:col-span-2 xl:col-span-1">
          <Label for="audit-query">综合搜索</Label>
          <div class="relative">
            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input id="audit-query" v-model="queryFilter" class="pl-9" placeholder="事件 ID、动作、目标、请求号或操作者" @keyup.enter="applyFilters" />
          </div>
        </div>
        <div class="space-y-2">
          <Label for="audit-action">动作</Label>
          <Input id="audit-action" v-model="actionFilter" placeholder="例如 archive.search" @keyup.enter="applyFilters" />
        </div>
        <div class="space-y-2">
          <Label for="audit-target-type">目标类型</Label>
          <Input id="audit-target-type" v-model="targetTypeFilter" placeholder="例如 password_candidate" @keyup.enter="applyFilters" />
        </div>
        <div class="space-y-2">
          <Label>结果</Label>
          <Select v-model="resultFilter">
            <SelectTrigger aria-label="审计结果筛选">
              <SelectValue placeholder="全部结果" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部结果</SelectItem>
              <SelectItem value="success">成功</SelectItem>
              <SelectItem value="failure">失败</SelectItem>
              <SelectItem value="blocked">阻止</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label for="audit-created-from">开始时间</Label>
          <Input id="audit-created-from" v-model="createdFromFilter" type="datetime-local" />
        </div>
        <div class="space-y-2">
          <Label for="audit-created-to">结束时间</Label>
          <Input id="audit-created-to" v-model="createdToFilter" type="datetime-local" />
        </div>
      </div>
      <div class="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-4">
        <p class="text-sm text-muted-foreground">{{ rangeLabel }}；单次 CSV 最多导出 5,000 条。</p>
        <div class="flex gap-2">
          <Button variant="ghost" @click="resetFilters">重置</Button>
          <Button @click="applyFilters">
            <Search class="h-4 w-4" aria-hidden="true" />
            应用筛选
          </Button>
        </div>
      </div>
    </section>

    <section class="overflow-hidden rounded-3xl border border-white/70 bg-white/85 shadow-sm shadow-slate-200/70 backdrop-blur-xl">
      <div class="flex items-center justify-between border-b border-border/70 px-5 py-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Immutable events</p>
          <h2 class="mt-1 text-lg font-semibold text-foreground">事件列表</h2>
        </div>
        <FileSearch2 class="h-5 w-5 text-sky-700" aria-hidden="true" />
      </div>
      <div class="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead class="min-w-44">时间</TableHead>
              <TableHead class="min-w-52">动作</TableHead>
              <TableHead class="min-w-40">操作者</TableHead>
              <TableHead class="min-w-44">目标</TableHead>
              <TableHead>结果</TableHead>
              <TableHead class="text-right">详情</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableEmpty v-if="!loading && items.length === 0" :colspan="6">
              当前筛选条件下没有审计事件。
            </TableEmpty>
            <TableRow v-for="item in items" :key="item.id">
              <TableCell class="whitespace-nowrap text-sm text-muted-foreground">{{ formatDate(item.created_at) }}</TableCell>
              <TableCell>
                <p class="font-mono text-sm font-medium text-foreground">{{ item.action }}</p>
                <p class="mt-1 max-w-64 truncate text-xs text-muted-foreground">{{ item.request_id || "无请求号" }}</p>
              </TableCell>
              <TableCell>
                <p class="text-sm font-medium text-foreground">{{ item.actor_username || "系统/匿名" }}</p>
                <p class="mt-1 text-xs text-muted-foreground">{{ roleLabel(item.actor_role) }}</p>
              </TableCell>
              <TableCell>
                <p class="text-sm text-foreground">{{ item.target_type }}</p>
                <p class="mt-1 max-w-48 truncate font-mono text-xs text-muted-foreground">{{ item.target_id || "—" }}</p>
              </TableCell>
              <TableCell><Badge :variant="resultVariant(item.result)">{{ resultLabel(item.result) }}</Badge></TableCell>
              <TableCell class="text-right">
                <Button variant="ghost" size="sm" @click="openDetail(item)">
                  <Eye class="h-4 w-4" aria-hidden="true" />
                  查看
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
      <div class="flex flex-col gap-3 border-t border-border/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p class="text-sm text-muted-foreground">第 {{ page }} / {{ totalPages }} 页</p>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" :disabled="page <= 1 || loading" @click="changePage(page - 1)">上一页</Button>
          <Button variant="outline" size="sm" :disabled="page >= totalPages || loading" @click="changePage(page + 1)">下一页</Button>
        </div>
      </div>
    </section>

    <Sheet v-model:open="detailOpen">
      <SheetContent class="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>审计事件详情</SheetTitle>
          <SheetDescription>仅展示服务端最小披露和脱敏后的审计字段。</SheetDescription>
        </SheetHeader>
        <div v-if="detailLoading" class="mt-6 space-y-3" aria-live="polite">
          <div v-for="index in 5" :key="index" class="h-12 animate-pulse rounded-xl bg-muted" />
        </div>
        <div v-else-if="selected" class="mt-6 space-y-5">
          <div class="rounded-2xl border bg-muted/40 p-4">
            <div class="flex items-center justify-between gap-3">
              <p class="font-mono text-sm font-semibold text-foreground">{{ selected.action }}</p>
              <Badge :variant="resultVariant(selected.result)">{{ resultLabel(selected.result) }}</Badge>
            </div>
            <p class="mt-3 text-sm text-muted-foreground">{{ formatDate(selected.created_at) }}</p>
          </div>
          <dl class="grid gap-4 text-sm sm:grid-cols-2">
            <div><dt class="text-muted-foreground">事件 ID</dt><dd class="mt-1 break-all font-mono text-xs text-foreground">{{ selected.id }}</dd></div>
            <div><dt class="text-muted-foreground">请求号</dt><dd class="mt-1 break-all font-mono text-xs text-foreground">{{ selected.request_id || "—" }}</dd></div>
            <div><dt class="text-muted-foreground">操作者</dt><dd class="mt-1 text-foreground">{{ selected.actor_username || "系统/匿名" }}</dd></div>
            <div><dt class="text-muted-foreground">角色</dt><dd class="mt-1 text-foreground">{{ roleLabel(selected.actor_role) }}</dd></div>
            <div><dt class="text-muted-foreground">目标类型</dt><dd class="mt-1 text-foreground">{{ selected.target_type }}</dd></div>
            <div><dt class="text-muted-foreground">目标 ID</dt><dd class="mt-1 break-all font-mono text-xs text-foreground">{{ selected.target_id || "—" }}</dd></div>
            <div><dt class="text-muted-foreground">IP 网段</dt><dd class="mt-1 font-mono text-xs text-foreground">{{ selected.ip_prefix || "—" }}</dd></div>
            <div><dt class="text-muted-foreground">操作者 ID</dt><dd class="mt-1 break-all font-mono text-xs text-foreground">{{ selected.actor_id || "—" }}</dd></div>
          </dl>
          <div>
            <h3 class="text-sm font-semibold text-foreground">脱敏详情</h3>
            <pre class="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-2xl border bg-slate-950 p-4 text-xs leading-6 text-slate-100">{{ JSON.stringify(selected.details, null, 2) }}</pre>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  </section>
</template>
