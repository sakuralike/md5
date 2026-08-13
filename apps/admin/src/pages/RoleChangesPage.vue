<script setup lang="ts">
import { createClientId } from "@/lib/clientId";
import {
  type RoleChangeReasonCode,
  type RoleChangeRequestStatus,
  type RoleChangeReviewReasonCode,
  type UserRole,
} from "@password-detective/api-contract";
import { Check, RefreshCw, Search, X } from "lucide-vue-next";
import { onMounted } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRoleChanges } from "../composables/useRoleChanges";
import {
  approveRoleChangeRequest,
  createRoleChangeRequest,
  listRoleChangeRequests,
  rejectRoleChangeRequest,
} from "../services/roleChanges";
import { reauthenticateAdmin } from "../services/users";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const {
  items,
  selected,
  filterStatus,
  page,
  loading,
  busy,
  error,
  success,
  currentPassword,
  totpCode,
  reviewReason,
  createUserId,
  createExpectedRole,
  createRequestedRole,
  createReason,
  totalPages,
  rangeLabel,
  pendingSelected,
  selectRequest,
  loadRequests,
  changeFilter,
  changePage,
  review,
  createRequest,
} = useRoleChanges({
  accessToken: () => auth.accessToken,
  randomUUID: () => createClientId(),
  listRoleChangeRequests,
  createRoleChangeRequest,
  approveRoleChangeRequest,
  rejectRoleChangeRequest,
  reauthenticateAdmin,
});

const roleLabels: Record<UserRole, string> = {
  user: "普通用户",
  trusted_contributor: "可信贡献者",
  moderator: "版主",
  admin: "管理员",
  service: "服务账号",
};
const statusLabels: Record<RoleChangeRequestStatus, string> = {
  pending: "待复核",
  approved: "已批准",
  rejected: "已拒绝",
};
const reasonLabels: Record<RoleChangeReasonCode, string> = {
  trust_promotion: "信任等级提升",
  role_alignment: "职责对齐",
  duty_assignment: "职责分配",
  duty_removal: "职责移除",
  security_response: "安全响应",
};
const reviewReasonLabels: Record<RoleChangeReviewReasonCode, string> = {
  verified: "证据已核验",
  insufficient_evidence: "证据不足",
  policy_conflict: "策略冲突",
  security_response: "安全响应",
};
const roles: UserRole[] = ["user", "trusted_contributor", "moderator"];

onMounted(() => void loadRequests());
</script>

<template>
  <section class="space-y-6">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">N2 · 双人复核</p>
        <h1 class="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">角色变更审批工作台</h1>
        <p class="text-sm text-muted-foreground">角色变更先申请、后复核；批准后目标账号必须重新登录。</p>
      </div>
      <Button variant="outline" :disabled="loading" @click="loadRequests()">
        <RefreshCw :size="16" />
        刷新
      </Button>
    </header>

    <p v-if="error" class="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
      {{ error }}
    </p>
    <p v-if="success" class="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm text-foreground" aria-live="polite">
      {{ success }}
    </p>

    <div class="grid gap-6 xl:grid-cols-2">
      <article class="space-y-5 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
        <div class="flex items-start justify-between gap-4">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">申请入口</p>
            <h2 class="text-lg font-semibold tracking-tight">创建角色变更请求</h2>
          </div>
          <Search class="text-muted-foreground" :size="20" />
        </div>
        <p class="text-sm text-muted-foreground">仅支持普通用户、可信贡献者和版主之间的固定转换。</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <Label class="grid gap-2">
            目标用户 ID
            <Input v-model="createUserId" placeholder="合成用户 ID" autocomplete="off" />
          </Label>
          <Label class="grid gap-2">
            当前角色
            <Select v-model="createExpectedRole">
              <SelectTrigger aria-label="当前角色"><SelectValue placeholder="选择当前角色" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="role in roles" :key="role" :value="role">{{ roleLabels[role] }}</SelectItem>
              </SelectContent>
            </Select>
          </Label>
          <Label class="grid gap-2">
            申请角色
            <Select v-model="createRequestedRole">
              <SelectTrigger aria-label="申请角色"><SelectValue placeholder="选择申请角色" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="role in roles" :key="role" :value="role">{{ roleLabels[role] }}</SelectItem>
              </SelectContent>
            </Select>
          </Label>
          <Label class="grid gap-2">
            申请原因
            <Select v-model="createReason">
              <SelectTrigger aria-label="申请原因"><SelectValue placeholder="选择原因" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="(label, reason) in reasonLabels" :key="reason" :value="reason">{{ label }}</SelectItem>
              </SelectContent>
            </Select>
          </Label>
        </div>
      </article>

      <article class="space-y-5 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
        <div class="flex items-start justify-between gap-4">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">敏感操作</p>
            <h2 class="text-lg font-semibold tracking-tight">一次性再认证</h2>
          </div>
          <Badge variant="secondary">不持久化</Badge>
        </div>
        <p class="text-sm text-muted-foreground">申请、批准和拒绝均需要当前密码与 TOTP；浏览器不会保存凭据。</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <Label class="grid gap-2">
            当前密码
            <Input v-model="currentPassword" type="password" autocomplete="current-password" />
          </Label>
          <Label class="grid gap-2">
            TOTP 动态码（已启用时填写）
            <Input
              v-model="totpCode"
              inputmode="numeric"
              maxlength="6"
              autocomplete="one-time-code"
            />
          </Label>
        </div>
        <div class="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <Button :disabled="busy" @click="createRequest">创建请求</Button>
          <Button variant="outline" :disabled="busy || !pendingSelected" @click="review('approve')">
            <Check :size="16" />
            批准选中
          </Button>
          <Button variant="destructive" :disabled="busy || !pendingSelected" @click="review('reject')">
            <X :size="16" />
            拒绝选中
          </Button>
        </div>
      </article>
    </div>

    <article class="overflow-hidden rounded-lg border bg-card text-card-foreground shadow-sm">
      <div class="flex flex-col gap-4 border-b px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">请求队列</p>
          <h2 class="text-lg font-semibold tracking-tight">角色变更请求</h2>
        </div>
        <Select v-model="filterStatus" @update:model-value="changeFilter">
          <SelectTrigger class="w-full sm:w-44" aria-label="筛选角色变更状态"><SelectValue placeholder="筛选状态" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="pending">待复核</SelectItem>
            <SelectItem value="approved">已批准</SelectItem>
            <SelectItem value="rejected">已拒绝</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>请求</TableHead>
            <TableHead>目标账号</TableHead>
            <TableHead>角色转换</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>申请时间</TableHead>
            <TableHead>操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableEmpty v-if="loading" :colspan="6">正在加载角色变更请求…</TableEmpty>
          <TableEmpty v-else-if="!items.length" :colspan="6">暂无角色变更请求</TableEmpty>
          <TableRow
            v-for="item in items"
            v-else
            :key="item.id"
            :data-state="selected?.id === item.id ? 'selected' : undefined"
          >
            <TableCell class="font-mono">{{ item.id.slice(0, 8) }}</TableCell>
            <TableCell class="font-mono">{{ item.target_user_id.slice(0, 8) }}</TableCell>
            <TableCell>{{ roleLabels[item.expected_role] }} → {{ roleLabels[item.requested_role] }}</TableCell>
            <TableCell>
              <Badge :variant="item.status === 'approved' ? 'secondary' : item.status === 'rejected' ? 'destructive' : 'outline'">
                {{ statusLabels[item.status] }}
              </Badge>
            </TableCell>
            <TableCell>{{ new Date(item.created_at).toLocaleString("zh-CN") }}</TableCell>
            <TableCell><Button variant="ghost" size="sm" @click="selectRequest(item)">查看</Button></TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <div class="flex flex-col gap-3 border-t border-border/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <span class="text-sm text-muted-foreground">{{ loading ? "正在加载…" : rangeLabel }}</span>
        <div class="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" :disabled="page <= 1 || loading" @click="changePage(page - 1)">上一页</Button>
          <span class="inline-flex items-center text-sm text-muted-foreground">第 {{ page }} / {{ totalPages }} 页</span>
          <Button variant="outline" size="sm" :disabled="page >= totalPages || loading" @click="changePage(page + 1)">下一页</Button>
        </div>
      </div>
    </article>

    <article v-if="selected" class="space-y-5 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">审批详情</p>
          <h2 class="text-lg font-semibold tracking-tight">请求 {{ selected.id.slice(0, 8) }}</h2>
        </div>
        <Badge>{{ statusLabels[selected.status] }}</Badge>
      </div>
      <div class="grid gap-4 text-sm sm:grid-cols-2 xl:grid-cols-4">
        <span class="grid gap-1 text-muted-foreground">目标账号 <strong class="break-all font-mono font-medium text-foreground">{{ selected.target_user_id }}</strong></span>
        <span class="grid gap-1 text-muted-foreground">申请人 <strong class="break-all font-mono font-medium text-foreground">{{ selected.requested_by }}</strong></span>
        <span class="grid gap-1 text-muted-foreground">角色转换 <strong class="font-medium text-foreground">{{ roleLabels[selected.expected_role] }} → {{ roleLabels[selected.requested_role] }}</strong></span>
        <span class="grid gap-1 text-muted-foreground">申请原因 <strong class="font-medium text-foreground">{{ reasonLabels[selected.reason_code as RoleChangeReasonCode] ?? selected.reason_code }}</strong></span>
        <span class="grid gap-1 text-muted-foreground">申请时间 <strong class="font-medium text-foreground">{{ new Date(selected.created_at).toLocaleString("zh-CN") }}</strong></span>
        <span class="grid gap-1 text-muted-foreground">复核人 <strong class="break-all font-mono font-medium text-foreground">{{ selected.reviewed_by ?? "待复核" }}</strong></span>
        <span class="grid gap-1 text-muted-foreground">复核原因 <strong class="font-medium text-foreground">{{ selected.review_reason_code ? (reviewReasonLabels[selected.review_reason_code as RoleChangeReviewReasonCode] ?? selected.review_reason_code) : "—" }}</strong></span>
        <span class="grid gap-1 text-muted-foreground">复核时间 <strong class="font-medium text-foreground">{{ selected.reviewed_at ? new Date(selected.reviewed_at).toLocaleString("zh-CN") : "—" }}</strong></span>
      </div>
      <div v-if="pendingSelected" class="max-w-md border-t pt-5">
        <Label class="grid gap-2">
          复核结论
          <Select v-model="reviewReason">
            <SelectTrigger aria-label="复核原因"><SelectValue placeholder="选择复核原因" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="(label, reason) in reviewReasonLabels" :key="reason" :value="reason">{{ label }}</SelectItem>
            </SelectContent>
          </Select>
        </Label>
      </div>
    </article>
  </section>
</template>
