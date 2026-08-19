<script setup lang="ts">
import { createClientId } from "@/lib/clientId";
import {
  ApiError,
  type AdminSessionRevocationReasonCode,
  type AdminUserCreateRequest,
  type AdminUserDetail,
  type AdminUserListItem,
  type AdminUserProfileReasonCode,
  type AdminUserStatusReasonCode,
  type UserRole,
  type UserStatus,
} from "@password-detective/api-contract";
import {
  Ban,
  Eye,
  KeyRound,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  ShieldOff,
  UserPlus,
  UserRoundPen,
  Users,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import UserLevelsManagement from "@/components/UserLevelsManagement.vue";
import RegistrationManagement from "@/components/RegistrationManagement.vue";
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
  changeAdminUserStatus,
  createAdminUser,
  getAdminUser,
  listAdminUsers,
  reauthenticateAdmin,
  revokeAdminUserSessions,
  updateAdminUserProfile,
  type AdminUserFilters,
} from "../services/users";
import { useAdminAuthStore } from "../stores/auth";

type GovernanceAction = "disable" | "restore" | "revoke_sessions";

interface ReasonOption {
  value: AdminUserStatusReasonCode | AdminSessionRevocationReasonCode;
  label: string;
}

const auth = useAdminAuthStore();
const items = ref<AdminUserListItem[]>([]);
const selected = ref<AdminUserDetail | null>(null);
const detailOpen = ref(false);
const loading = ref(false);
const detailLoading = ref(false);
const error = ref("");
const page = ref(1);
const pageSize = 20;
const total = ref(0);
const queryFilter = ref("");
const statusFilter = ref("all");
const roleFilter = ref("all");
const actionMode = ref<GovernanceAction | null>(null);
const actionReason = ref("");
const currentPassword = ref("");
const totpCode = ref("");
const actionBusy = ref(false);
const actionError = ref("");
const actionSuccess = ref("");
const createUsername = ref("");
const createEmail = ref("");
const createPassword = ref("");
const createRole = ref<AdminUserCreateRequest["role"]>("user");
const createStatus = ref<AdminUserCreateRequest["status"]>("active");
const createEmailVerified = ref("true");
const createBusy = ref(false);
const createError = ref("");
const createSuccess = ref("");
const profileEditing = ref(false);
const profileEmail = ref("");
const profileEmailVerified = ref("keep");
const profileReason = ref<AdminUserProfileReasonCode>("profile_correction");
const profilePassword = ref("");
const profileTotp = ref("");
const profileBusy = ref(false);
const profileError = ref("");

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const rangeLabel = computed(() => {
  if (total.value === 0) return "暂无用户";
  const start = (page.value - 1) * pageSize + 1;
  const end = Math.min(page.value * pageSize, total.value);
  return `第 ${start}–${end} 条，共 ${total.value} 条`;
});
const selectedIsProtected = computed(() => {
  if (!selected.value) return true;
  return (
    selected.value.id === auth.user?.id ||
    selected.value.role === "admin" ||
    selected.value.role === "service"
  );
});
const actionTitle = computed(() => {
  if (actionMode.value === "disable") return "确认停用账号";
  if (actionMode.value === "restore") return "确认恢复账号";
  if (actionMode.value === "revoke_sessions") return "确认撤销全部活跃会话";
  return "危险操作确认";
});
const reasonOptions = computed<ReasonOption[]>(() => {
  if (actionMode.value === "disable") {
    return [
      { value: "security_risk", label: "安全风险" },
      { value: "abuse_confirmed", label: "滥用行为已确认" },
      { value: "policy_violation", label: "违反平台规则" },
      { value: "manual_review", label: "人工复核决定" },
    ];
  }
  if (actionMode.value === "restore") {
    return [
      { value: "appeal_approved", label: "申诉通过" },
      { value: "manual_review", label: "人工复核决定" },
    ];
  }
  return [
    { value: "security_risk", label: "安全风险" },
    { value: "user_request", label: "用户主动请求" },
    { value: "incident_response", label: "安全事件响应" },
    { value: "manual_review", label: "人工复核决定" },
  ];
});

const statusLabels: Record<UserStatus, string> = {
  active: "正常",
  locked: "锁定",
  disabled: "停用",
};
const roleLabels: Record<UserRole, string> = {
  user: "普通用户",
  trusted_contributor: "可信贡献者",
  moderator: "版主",
  admin: "管理员",
  service: "服务账号",
};

function describeError(value: unknown): string {
  if (value instanceof ApiError) return value.body.message;
  return value instanceof Error ? value.message : "用户治理服务暂时不可用";
}

function currentFilters(): AdminUserFilters {
  return {
    query: queryFilter.value || undefined,
    status: statusFilter.value === "all" ? undefined : (statusFilter.value as UserStatus),
    role: roleFilter.value === "all" ? undefined : (roleFilter.value as UserRole),
    page: page.value,
    pageSize,
  };
}

async function loadUsers(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listAdminUsers(currentFilters(), auth.accessToken);
    items.value = response.items;
    total.value = response.total;
    if (page.value > totalPages.value) {
      page.value = totalPages.value;
      await loadUsers();
    }
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function applyFilters(): Promise<void> {
  page.value = 1;
  await loadUsers();
}

async function resetFilters(): Promise<void> {
  queryFilter.value = "";
  statusFilter.value = "all";
  roleFilter.value = "all";
  page.value = 1;
  await loadUsers();
}

async function changePage(nextPage: number): Promise<void> {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value);
  await loadUsers();
}

function resetActionForm(): void {
  actionMode.value = null;
  actionReason.value = "";
  currentPassword.value = "";
  totpCode.value = "";
  actionError.value = "";
}

function resetProfileForm(): void {
  profileEditing.value = false;
  profileEmail.value = "";
  profileEmailVerified.value = "keep";
  profileReason.value = "profile_correction";
  profilePassword.value = "";
  profileTotp.value = "";
  profileError.value = "";
}

async function openDetail(item: AdminUserListItem): Promise<void> {
  detailOpen.value = true;
  selected.value = null;
  detailLoading.value = true;
  actionSuccess.value = "";
  resetActionForm();
  resetProfileForm();
  error.value = "";
  try {
    selected.value = await getAdminUser(item.id, auth.accessToken);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    detailLoading.value = false;
  }
}

async function submitProfileUpdate(): Promise<void> {
  if (!selected.value || !auth.accessToken) return;
  profileBusy.value = true;
  profileError.value = "";
  actionSuccess.value = "";
  const userId = selected.value.id;
  try {
    const grant = await reauthenticateAdmin(
      {
        currentPassword: profilePassword.value,
        ...(profileTotp.value ? { totpCode: profileTotp.value } : {}),
      },
      auth.accessToken,
    );
    await updateAdminUserProfile(
      userId,
      {
        expectedUpdatedAt: selected.value.updated_at,
        ...(profileEmail.value.trim() ? { email: profileEmail.value.trim() } : {}),
        ...(profileEmailVerified.value === "keep"
          ? {}
          : { emailVerified: profileEmailVerified.value === "true" }),
        reasonCode: profileReason.value,
        reauthToken: grant.reauth_token,
      },
      auth.accessToken,
      `admin-profile-${createClientId()}`,
    );
    actionSuccess.value = "用户非权限资料已更新，审计事件已记录。";
    resetProfileForm();
    await refreshSelectedUser(userId);
  } catch (value) {
    profileError.value = describeError(value);
    profilePassword.value = "";
    profileTotp.value = "";
  } finally {
    profileBusy.value = false;
  }
}

function beginAction(mode: GovernanceAction): void {
  actionMode.value = mode;
  actionReason.value = "";
  currentPassword.value = "";
  totpCode.value = "";
  actionError.value = "";
  actionSuccess.value = "";
}

async function refreshSelectedUser(userId: string): Promise<void> {
  selected.value = await getAdminUser(userId, auth.accessToken);
  await loadUsers();
}

async function submitAction(): Promise<void> {
  if (!selected.value || !actionMode.value) return;
  if (!actionReason.value || !currentPassword.value) {
    actionError.value = "请选择原因并填写当前密码";
    return;
  }

  actionBusy.value = true;
  actionError.value = "";
  actionSuccess.value = "";
  const userId = selected.value.id;
  const mode = actionMode.value;
  try {
    const grant = await reauthenticateAdmin(
      {
        currentPassword: currentPassword.value,
        ...(totpCode.value ? { totpCode: totpCode.value } : {}),
      },
      auth.accessToken,
    );
    const idempotencyKey = `admin-${mode}-${createClientId()}`;
    if (mode === "revoke_sessions") {
      const result = await revokeAdminUserSessions(
        userId,
        {
          expectedActiveSessionCount: selected.value.active_session_count,
          reasonCode: actionReason.value as AdminSessionRevocationReasonCode,
          reauthToken: grant.reauth_token,
        },
        auth.accessToken,
        idempotencyKey,
      );
      actionSuccess.value = `已撤销 ${result.revoked_session_count} 个活跃会话，审计事件已记录。`;
    } else {
      const result = await changeAdminUserStatus(
        userId,
        {
          expectedStatus: selected.value.status,
          status: mode === "disable" ? "disabled" : "active",
          reasonCode: actionReason.value as AdminUserStatusReasonCode,
          reauthToken: grant.reauth_token,
        },
        auth.accessToken,
        idempotencyKey,
      );
      actionSuccess.value =
        mode === "disable"
          ? `账号已停用，并撤销 ${result.revoked_session_count} 个活跃会话。`
          : "账号已恢复为正常状态，审计事件已记录。";
    }
    resetActionForm();
    try {
      await refreshSelectedUser(userId);
    } catch (value) {
      error.value = `操作已成功，但刷新用户详情失败：${describeError(value)}`;
    }
  } catch (value) {
    actionError.value = describeError(value);
    currentPassword.value = "";
    totpCode.value = "";
  } finally {
    actionBusy.value = false;
  }
}

function formatDate(value: string | null): string {
  if (!value) return "暂无记录";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusVariant(status: UserStatus): "default" | "secondary" | "destructive" | "outline" {
  if (status === "active") return "default";
  if (status === "disabled") return "destructive";
  return "secondary";
}

async function submitCreateUser(): Promise<void> {
  if (!auth.accessToken) return;
  createBusy.value = true;
  createError.value = "";
  createSuccess.value = "";
  try {
    const created = await createAdminUser(
      {
        username: createUsername.value.trim(),
        email: createEmail.value.trim(),
        password: createPassword.value,
        role: createRole.value,
        status: createStatus.value,
        email_verified: createEmailVerified.value === "true",
      },
      auth.accessToken,
    );
    createSuccess.value = `用户 ${created.username} 已创建，初始密码不会在后台再次显示。`;
    createUsername.value = "";
    createEmail.value = "";
    createPassword.value = "";
    createRole.value = "user";
    createStatus.value = "active";
    createEmailVerified.value = "true";
    await loadUsers();
  } catch (value) {
    createError.value = describeError(value);
  } finally {
    createBusy.value = false;
  }
}

onMounted(() => void loadUsers());
</script>

<template>
  <section class="space-y-6">
    <header class="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
      <div>
        <div class="flex items-center gap-2 text-sm font-medium text-sky-700">
          <Users class="h-4 w-4" /> N2 用户审批
        </div>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">用户审批工作台</h1>
        <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          管理员可手动创建普通、可信贡献者或版主账号，并在当前密码、可选 TOTP、原因码、一次性再认证和幂等门禁下停用账号、恢复账号或撤销活跃会话。
        </p>
      </div>
      <Button variant="outline" :disabled="loading" @click="loadUsers">
        <RefreshCw class="mr-2 h-4 w-4" :class="loading && 'animate-spin'" />
        {{ loading ? "刷新中" : "刷新" }}
      </Button>
    </header>

    <section class="scroll-mt-28 space-y-4 rounded-2xl border bg-card p-5 text-card-foreground shadow-sm">
      <div class="flex items-start gap-3">
        <span class="rounded-lg bg-primary/10 p-2 text-primary"><UserPlus class="h-5 w-5" /></span>
        <div>
          <h2 class="font-semibold">手动创建用户</h2>
          <p class="mt-1 text-sm leading-6 text-muted-foreground">
            可创建普通用户、可信贡献者或版主。管理员与服务账号仍必须走角色审批或受控运维流程。
          </p>
        </div>
      </div>
      <form class="grid gap-4 md:grid-cols-2 xl:grid-cols-3" @submit.prevent="submitCreateUser">
        <div class="space-y-2">
          <Label for="create-username">用户名</Label>
          <Input id="create-username" v-model="createUsername" minlength="3" maxlength="32" required autocomplete="off" />
        </div>
        <div class="space-y-2">
          <Label for="create-email">邮箱</Label>
          <Input id="create-email" v-model="createEmail" type="email" required autocomplete="off" />
        </div>
        <div class="space-y-2">
          <Label for="create-password">初始密码</Label>
          <Input id="create-password" v-model="createPassword" type="password" minlength="12" maxlength="128" required autocomplete="new-password" />
        </div>
        <div class="space-y-2">
          <Label>账号角色</Label>
          <Select v-model="createRole">
            <SelectTrigger aria-label="新用户角色"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="user">普通用户</SelectItem>
              <SelectItem value="trusted_contributor">可信贡献者</SelectItem>
              <SelectItem value="moderator">版主</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>初始状态</Label>
          <Select v-model="createStatus">
            <SelectTrigger aria-label="新用户状态"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="active">正常</SelectItem>
              <SelectItem value="disabled">停用</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>邮箱验证状态</Label>
          <Select v-model="createEmailVerified">
            <SelectTrigger aria-label="邮箱验证状态"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="true">已验证</SelectItem>
              <SelectItem value="false">待验证</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="md:col-span-2 xl:col-span-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p v-if="createError" class="text-sm text-destructive" role="alert">{{ createError }}</p>
            <p v-if="createSuccess" class="text-sm text-primary" role="status">{{ createSuccess }}</p>
          </div>
          <Button type="submit" :disabled="createBusy">
            <UserPlus class="mr-2 h-4 w-4" />{{ createBusy ? "正在创建…" : "创建用户" }}
          </Button>
        </div>
      </form>
    </section>

    <RegistrationManagement />

    <div v-if="error" class="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
      {{ error }}
    </div>

    <section class="rounded-3xl border border-white/70 bg-white/80 p-5 shadow-sm shadow-slate-200/70 backdrop-blur-xl">
      <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_12rem_12rem_auto_auto] lg:items-end">
        <div class="space-y-2">
          <Label for="user-query">搜索用户</Label>
          <div class="relative">
            <Search class="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <Input id="user-query" v-model="queryFilter" class="pl-9" placeholder="用户名、邮箱或 UID" @keyup.enter="applyFilters" />
          </div>
        </div>
        <div class="space-y-2">
          <Label>账号状态</Label>
          <Select v-model="statusFilter">
            <SelectTrigger aria-label="账号状态"><SelectValue placeholder="全部状态" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="active">正常</SelectItem>
              <SelectItem value="locked">锁定</SelectItem>
              <SelectItem value="disabled">停用</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>账号角色</Label>
          <Select v-model="roleFilter">
            <SelectTrigger aria-label="账号角色"><SelectValue placeholder="全部角色" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部角色</SelectItem>
              <SelectItem value="user">普通用户</SelectItem>
              <SelectItem value="trusted_contributor">可信贡献者</SelectItem>
              <SelectItem value="moderator">版主</SelectItem>
              <SelectItem value="admin">管理员</SelectItem>
              <SelectItem value="service">服务账号</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button @click="applyFilters"><Search class="mr-2 h-4 w-4" />查询</Button>
        <Button variant="ghost" @click="resetFilters">重置</Button>
      </div>
    </section>

    <section class="overflow-hidden rounded-3xl border border-white/70 bg-white/80 shadow-sm shadow-slate-200/70 backdrop-blur-xl">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>用户</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>角色</TableHead>
            <TableHead>MFA</TableHead>
            <TableHead>活跃会话</TableHead>
            <TableHead>最近活跃</TableHead>
            <TableHead class="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableEmpty v-if="!loading && items.length === 0" :colspan="7">暂无符合条件的用户</TableEmpty>
          <TableRow v-for="item in items" :key="item.id">
            <TableCell>
              <div class="font-medium text-slate-950">{{ item.username }}</div>
              <div class="text-xs text-slate-500">{{ item.masked_email }}</div>
              <div class="mt-1 break-all font-mono text-xs text-muted-foreground">UID：{{ item.uid ?? item.id }}</div>
            </TableCell>
            <TableCell><Badge :variant="statusVariant(item.status)">{{ statusLabels[item.status] }}</Badge></TableCell>
            <TableCell class="text-slate-600">{{ roleLabels[item.role] }}</TableCell>
            <TableCell>
              <span class="inline-flex items-center gap-1 text-sm" :class="item.totp_enabled ? 'text-emerald-700' : 'text-slate-500'">
                <ShieldCheck class="h-4 w-4" /> {{ item.totp_enabled ? "已启用" : "未启用" }}
              </span>
            </TableCell>
            <TableCell class="text-slate-600">{{ item.active_session_count }}</TableCell>
            <TableCell class="text-slate-600">{{ formatDate(item.last_active_at) }}</TableCell>
            <TableCell class="text-right">
              <Button variant="outline" size="sm" @click="openDetail(item)"><Eye class="mr-2 h-4 w-4" />详情与治理</Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <div class="flex flex-col gap-3 border-t border-slate-100 px-5 py-4 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <span>{{ loading ? "正在加载用户…" : rangeLabel }}</span>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" :disabled="page <= 1 || loading" @click="changePage(page - 1)">上一页</Button>
          <Button variant="outline" size="sm" :disabled="page >= totalPages || loading" @click="changePage(page + 1)">下一页</Button>
        </div>
      </div>
    </section>

    <UserLevelsManagement />

    <Sheet :open="detailOpen" @update:open="detailOpen = $event">
      <SheetContent side="right" class="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>用户详情与治理</SheetTitle>
          <SheetDescription>响应仅展示掩码邮箱；危险操作必须逐次重新认证并写入审计。</SheetDescription>
        </SheetHeader>
        <div v-if="detailLoading" class="py-12 text-center text-sm text-slate-500">正在加载详情…</div>
        <div v-else-if="selected" class="mt-6 space-y-6">
          <div class="rounded-2xl bg-slate-50 p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h2 class="text-lg font-semibold text-slate-950">{{ selected.username }}</h2>
                <p class="mt-1 text-sm text-slate-500">{{ selected.masked_email }}</p>
                <p class="mt-1 break-all font-mono text-xs text-muted-foreground">UID：{{ selected.uid ?? selected.id }}</p>
              </div>
              <Badge :variant="statusVariant(selected.status)">{{ statusLabels[selected.status] }}</Badge>
            </div>
            <dl class="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <div><dt class="text-muted-foreground">用户 UID</dt><dd class="break-all font-mono text-xs text-foreground">{{ selected.uid ?? selected.id }}</dd></div>
              <div><dt class="text-slate-500">角色</dt><dd class="font-medium text-slate-900">{{ roleLabels[selected.role] }}</dd></div>
              <div><dt class="text-slate-500">MFA</dt><dd class="font-medium text-slate-900">{{ selected.totp_enabled ? "已启用" : "未启用" }}</dd></div>
              <div><dt class="text-slate-500">注册时间</dt><dd class="font-medium text-slate-900">{{ formatDate(selected.created_at) }}</dd></div>
              <div><dt class="text-slate-500">最近活跃</dt><dd class="font-medium text-slate-900">{{ formatDate(selected.last_active_at) }}</dd></div>
              <div><dt class="text-muted-foreground">用户等级</dt><dd class="font-medium text-foreground">{{ selected.level.current.name }}</dd></div>
              <div><dt class="text-muted-foreground">成长值</dt><dd class="font-medium text-foreground">{{ selected.level.growth_points }}</dd></div>
            </dl>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div v-for="metric in [
              ['积分余额', selected.points_balance],
              ['声望事件', selected.reputation_event_count],
              ['提交记录', selected.submission_count],
              ['举报/申诉', selected.trust_case_count],
              ['全部会话', selected.total_session_count],
              ['活跃会话', selected.active_session_count],
              ['隐私导出队列', selected.pending_privacy_export_count],
              ['注销请求队列', selected.pending_deletion_request_count],
            ]" :key="metric[0]" class="rounded-2xl border border-slate-100 bg-white p-4">
              <dt class="text-sm text-slate-500">{{ metric[0] }}</dt>
              <dd class="mt-2 text-2xl font-semibold text-slate-950">{{ metric[1] }}</dd>
            </div>
          </div>

          <div v-if="actionSuccess" class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800" role="status" aria-live="polite">
            {{ actionSuccess }}
          </div>

          <section v-if="!selectedIsProtected" class="space-y-4 rounded-lg border p-4">
            <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
              <div class="flex items-start gap-3">
                <UserRoundPen class="mt-0.5 h-5 w-5 text-primary" />
                <div>
                  <h3 class="font-semibold">编辑非权限资料</h3>
                  <p class="mt-1 text-sm text-muted-foreground">仅可修改邮箱及其验证状态，不包含角色、密码、积分或安全凭据。</p>
                </div>
              </div>
              <Button v-if="!profileEditing" size="sm" variant="outline" @click="profileEditing = true">编辑资料</Button>
            </div>
            <form v-if="profileEditing" class="space-y-4 border-t pt-4" @submit.prevent="submitProfileUpdate">
              <div class="grid gap-4 sm:grid-cols-2">
                <div class="space-y-2">
                  <Label for="profile-email">新邮箱（可选）</Label>
                  <Input id="profile-email" v-model="profileEmail" type="email" autocomplete="off" :placeholder="selected.masked_email" />
                </div>
                <div class="space-y-2">
                  <Label>邮箱验证状态</Label>
                  <Select v-model="profileEmailVerified">
                    <SelectTrigger aria-label="资料编辑邮箱验证状态"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="keep">保持当前状态</SelectItem>
                      <SelectItem value="true">标记为已验证</SelectItem>
                      <SelectItem value="false">标记为待验证</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-2">
                  <Label>修改原因</Label>
                  <Select v-model="profileReason">
                    <SelectTrigger aria-label="资料修改原因"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="profile_correction">资料纠正</SelectItem>
                      <SelectItem value="user_request">用户请求</SelectItem>
                      <SelectItem value="compliance_review">合规复核</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-2">
                  <Label for="profile-admin-password">管理员当前密码</Label>
                  <Input id="profile-admin-password" v-model="profilePassword" type="password" autocomplete="current-password" required />
                </div>
                <div class="space-y-2 sm:col-span-2">
                  <Label for="profile-admin-totp">TOTP 验证码（已启用时填写）</Label>
                  <Input id="profile-admin-totp" v-model="profileTotp" inputmode="numeric" autocomplete="one-time-code" maxlength="8" />
                </div>
              </div>
              <p v-if="profileError" class="text-sm text-destructive" role="alert">{{ profileError }}</p>
              <div class="flex justify-end gap-2">
                <Button type="button" variant="ghost" :disabled="profileBusy" @click="resetProfileForm">取消</Button>
                <Button type="submit" :disabled="profileBusy">{{ profileBusy ? "保存中" : "保存资料" }}</Button>
              </div>
            </form>
          </section>

          <section class="rounded-2xl border border-rose-200 bg-rose-50/70 p-4">
            <div class="flex items-start gap-3">
              <ShieldOff class="mt-0.5 h-5 w-5 text-rose-700" />
              <div>
                <h3 class="font-semibold text-rose-950">受控治理操作</h3>
                <p class="mt-1 text-sm leading-6 text-rose-800">
                  每次操作都需要当前密码；账号已启用 TOTP 时还需动态验证码，凭据不会保存；管理员自身、其他管理员和服务账号受保护。
                </p>
              </div>
            </div>

            <div v-if="selectedIsProtected" class="mt-4 rounded-xl border border-rose-200 bg-white/70 px-4 py-3 text-sm text-rose-800">
              当前对象属于受保护账号，本入口仅保留只读能力。
            </div>
            <div v-else class="mt-4 flex flex-wrap gap-2">
              <Button v-if="selected.status === 'active'" variant="destructive" size="sm" @click="beginAction('disable')">
                <Ban class="mr-2 h-4 w-4" />停用账号
              </Button>
              <Button v-else variant="outline" size="sm" @click="beginAction('restore')">
                <RotateCcw class="mr-2 h-4 w-4" />恢复账号
              </Button>
              <Button variant="outline" size="sm" :disabled="selected.active_session_count === 0" @click="beginAction('revoke_sessions')">
                <KeyRound class="mr-2 h-4 w-4" />撤销活跃会话
              </Button>
            </div>

            <div v-if="actionMode" class="mt-4 space-y-4 rounded-2xl border border-rose-200 bg-white p-4 shadow-sm">
              <div>
                <h4 class="font-semibold text-slate-950">{{ actionTitle }}</h4>
                <p class="mt-1 text-sm text-slate-500">提交前会签发仅限本次用户治理操作的一次性再认证凭据。</p>
              </div>
              <div class="space-y-2">
                <Label>操作原因</Label>
                <Select v-model="actionReason">
                  <SelectTrigger aria-label="操作原因"><SelectValue placeholder="选择结构化原因码" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="option in reasonOptions" :key="option.value" :value="option.value">{{ option.label }}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div class="grid gap-4 sm:grid-cols-2">
                <div class="space-y-2">
                  <Label for="admin-current-password">当前密码</Label>
                  <Input id="admin-current-password" v-model="currentPassword" type="password" autocomplete="current-password" />
                </div>
                <div class="space-y-2">
                  <Label for="admin-totp-code">TOTP 验证码（已启用时填写）</Label>
                  <Input id="admin-totp-code" v-model="totpCode" inputmode="numeric" autocomplete="one-time-code" maxlength="8" />
                </div>
              </div>
              <div v-if="actionError" class="rounded-xl border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert" aria-live="assertive">
                {{ actionError }}
              </div>
              <div class="flex flex-wrap justify-end gap-2">
                <Button variant="ghost" :disabled="actionBusy" @click="resetActionForm">取消</Button>
                <Button :variant="actionMode === 'disable' ? 'destructive' : 'default'" :disabled="actionBusy" @click="submitAction">
                  {{ actionBusy ? "正在执行安全校验…" : "确认并执行" }}
                </Button>
              </div>
            </div>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  </section>
</template>
