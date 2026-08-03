<script setup lang="ts">
import type {
  AuthorizationDeclaration,
  PrivacyDeletionRequest,
  PrivacyExport,
} from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  cancelAccountDeletion,
  confirmAuthorizationDeclaration,
  downloadPrivacyExport,
  getCurrentDeletionRequest,
  listAuthorizationDeclarations,
  requestAccountDeletion,
  requestPrivacyExport,
} from "../services/account";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const declarations = ref<AuthorizationDeclaration[]>([]);
const currentExport = ref<PrivacyExport | null>(null);
const deletion = ref<PrivacyDeletionRequest | null>(null);
const currentPassword = ref("");
const totpCode = ref("");
const busy = ref("");
const error = ref("");
const success = ref("");

const purposes = [
  { id: "archive_search", name: "档案检索", description: "确认仅处理本人拥有或获授权的数据。" },
  { id: "privacy_export", name: "个人数据导出", description: "确认导出仅用于本人查阅与备份。" },
] as const;

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function messageFrom(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

function clearFeedback(): void {
  error.value = "";
  success.value = "";
}

async function load(): Promise<void> {
  busy.value = "load";
  clearFeedback();
  try {
    const [declarationResponse, deletionResponse] = await Promise.all([
      listAuthorizationDeclarations(auth.accessToken),
      getCurrentDeletionRequest(auth.accessToken),
    ]);
    declarations.value = declarationResponse.items;
    deletion.value = deletionResponse;
  } catch (caught) {
    error.value = messageFrom(caught, "无法加载隐私设置");
  } finally {
    busy.value = "";
  }
}

function isConfirmed(purpose: string): boolean {
  return declarations.value.some((item) => item.purpose === purpose && item.active);
}

async function confirmPurpose(purpose: string): Promise<void> {
  busy.value = `purpose:${purpose}`;
  clearFeedback();
  try {
    const result = await confirmAuthorizationDeclaration(auth.accessToken, {
      purpose,
      source: "web",
      accepted: true,
    });
    declarations.value = [
      result,
      ...declarations.value.filter((item) => item.id !== result.id),
    ];
    success.value = "授权声明已确认";
  } catch (caught) {
    error.value = messageFrom(caught, "授权声明确认失败");
  } finally {
    busy.value = "";
  }
}

async function createExport(): Promise<void> {
  busy.value = "export";
  clearFeedback();
  try {
    currentExport.value = await requestPrivacyExport(auth.accessToken);
    success.value = currentExport.value.download_available
      ? "个人数据导出已生成，请在过期前完成一次性下载"
      : "个人数据导出请求已进入处理队列";
  } catch (caught) {
    error.value = messageFrom(caught, "数据导出请求失败");
  } finally {
    busy.value = "";
  }
}

async function downloadExport(): Promise<void> {
  if (!currentExport.value?.download_token) return;
  busy.value = "download";
  clearFeedback();
  try {
    const file = await downloadPrivacyExport(
      auth.accessToken,
      currentExport.value.id,
      currentExport.value.download_token,
    );
    const url = URL.createObjectURL(file.blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = file.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    currentExport.value = {
      ...currentExport.value,
      status: "downloaded",
      download_available: false,
      download_token: null,
      downloaded_at: new Date().toISOString(),
    };
    success.value = "导出文件已下载，本次下载凭证已销毁";
  } catch (caught) {
    error.value = messageFrom(caught, "导出文件下载失败");
  } finally {
    busy.value = "";
  }
}

async function createDeletion(): Promise<void> {
  busy.value = "deletion";
  clearFeedback();
  try {
    deletion.value = await requestAccountDeletion(auth.accessToken, {
      current_password: currentPassword.value,
      totp_code: totpCode.value || null,
    });
    currentPassword.value = "";
    totpCode.value = "";
    success.value = "账号删除请求已创建，可在撤销期限前取消";
  } catch (caught) {
    error.value = messageFrom(caught, "账号删除请求失败");
  } finally {
    busy.value = "";
  }
}

async function cancelDeletion(): Promise<void> {
  if (!deletion.value) return;
  busy.value = "cancel-deletion";
  clearFeedback();
  try {
    deletion.value = await cancelAccountDeletion(auth.accessToken, deletion.value.id);
    success.value = "账号删除请求已取消";
  } catch (caught) {
    error.value = messageFrom(caught, "取消账号删除请求失败");
  } finally {
    busy.value = "";
  }
}

onMounted(load);
</script>

<template>
  <section class="mx-auto max-w-6xl space-y-6">
    <div class="space-y-2">
      <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Privacy center</p>
      <h1 class="text-3xl font-semibold tracking-tight text-foreground">隐私与授权中心</h1>
      <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
        管理用途化授权声明、个人数据导出与账号删除流程。系统不会在这些记录中保存密码或 TOTP 密钥。
      </p>
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>操作未完成</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Alert v-if="success">
      <AlertTitle>已完成</AlertTitle>
      <AlertDescription>{{ success }}</AlertDescription>
    </Alert>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>授权声明</CardTitle>
          <CardDescription>按用途确认当前声明版本，服务端记录版本、来源与确认时间。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-3">
          <div
            v-for="purpose in purposes"
            :key="purpose.id"
            class="flex flex-col gap-3 rounded-xl border border-border/70 bg-background/55 p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div class="flex items-center gap-2">
                <p class="font-medium text-foreground">{{ purpose.name }}</p>
                <Badge :variant="isConfirmed(purpose.id) ? 'default' : 'secondary'">
                  {{ isConfirmed(purpose.id) ? "已确认" : "待确认" }}
                </Badge>
              </div>
              <p class="mt-1 text-sm text-muted-foreground">{{ purpose.description }}</p>
            </div>
            <Button
              variant="outline"
              :disabled="isConfirmed(purpose.id) || busy === `purpose:${purpose.id}`"
              @click="confirmPurpose(purpose.id)"
            >
              {{ isConfirmed(purpose.id) ? "当前有效" : "确认声明" }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>个人数据导出</CardTitle>
          <CardDescription>异步生成 JSON 文件；凭证短时有效、仅可下载一次。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-3 text-sm">
          <div v-if="currentExport" class="rounded-xl border border-border/70 bg-background/55 p-4">
            <div class="flex items-center justify-between gap-3">
              <span class="text-muted-foreground">当前状态</span>
              <Badge>{{ currentExport.status }}</Badge>
            </div>
            <p class="mt-3 text-xs text-muted-foreground">
              过期时间：{{ formatDate(currentExport.expires_at) }}
            </p>
            <p v-if="currentExport.artifact_sha256" class="mt-1 break-all font-mono text-xs text-muted-foreground">
              SHA-256：{{ currentExport.artifact_sha256 }}
            </p>
          </div>
          <p v-else class="rounded-xl border border-dashed border-border p-5 text-muted-foreground">
            尚未申请个人数据导出。
          </p>
        </CardContent>
        <CardFooter class="flex flex-wrap gap-3">
          <Button :disabled="busy === 'export'" @click="createExport">
            {{ busy === "export" ? "生成中…" : "申请导出" }}
          </Button>
          <Button
            variant="outline"
            :disabled="!currentExport?.download_available || busy === 'download'"
            @click="downloadExport"
          >
            一次性下载
          </Button>
        </CardFooter>
      </Card>
    </div>

    <Card class="border-destructive/30">
      <CardHeader>
        <CardTitle>账号删除请求</CardTitle>
        <CardDescription>
          创建请求前必须重新验证当前密码；启用 TOTP 时还需动态验证码。撤销期结束后，账号将被停用并去标识化。
        </CardDescription>
      </CardHeader>
      <CardContent class="grid gap-5 lg:grid-cols-2">
        <div v-if="deletion" class="rounded-xl border border-border/70 bg-background/55 p-4 text-sm">
          <div class="flex items-center justify-between gap-3">
            <span class="text-muted-foreground">请求状态</span>
            <Badge :variant="deletion.status === 'cancelled' ? 'secondary' : 'destructive'">
              {{ deletion.status }}
            </Badge>
          </div>
          <p class="mt-3 text-muted-foreground">创建时间：{{ formatDate(deletion.requested_at) }}</p>
          <p class="mt-1 text-muted-foreground">撤销截止：{{ formatDate(deletion.cancel_before) }}</p>
        </div>
        <div v-else class="grid gap-4">
          <div class="space-y-2">
            <Label for="privacy-current-password">当前密码</Label>
            <Input
              id="privacy-current-password"
              v-model="currentPassword"
              type="password"
              autocomplete="current-password"
            />
          </div>
          <div v-if="auth.user?.totp_enabled" class="space-y-2">
            <Label for="privacy-totp-code">动态验证码</Label>
            <Input
              id="privacy-totp-code"
              v-model="totpCode"
              inputmode="numeric"
              autocomplete="one-time-code"
            />
          </div>
        </div>
      </CardContent>
      <CardFooter>
        <Button
          v-if="!deletion"
          variant="destructive"
          :disabled="!currentPassword || busy === 'deletion'"
          @click="createDeletion"
        >
          创建删除请求
        </Button>
        <Button
          v-else-if="deletion.can_cancel"
          variant="outline"
          :disabled="busy === 'cancel-deletion'"
          @click="cancelDeletion"
        >
          取消删除请求
        </Button>
      </CardFooter>
    </Card>
  </section>
</template>
