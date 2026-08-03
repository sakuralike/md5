<script setup lang="ts">
import type { Session, TotpSetupResponse } from "@password-detective/api-contract";
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
import { Separator } from "../components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const sessions = ref<Session[]>([]);
const username = ref("");
const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const passwordTotpCode = ref("");
const totpCode = ref("");
const totpCurrentPassword = ref("");
const setup = ref<TotpSetupResponse | null>(null);
const error = ref("");
const success = ref("");
const busy = ref(false);
const busyId = ref("");

function clearFeedback(): void {
  error.value = "";
  success.value = "";
}

function messageFrom(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

async function load(): Promise<void> {
  try {
    await auth.loadProfile();
    username.value = auth.user?.username ?? "";
    sessions.value = await auth.listSessions();
  } catch (caught) {
    error.value = messageFrom(caught, "无法加载账号安全信息");
  }
}

async function saveProfile(): Promise<void> {
  clearFeedback();
  busy.value = true;
  try {
    await auth.updateProfile({ username: username.value });
    success.value = "个人资料已保存";
  } catch (caught) {
    error.value = messageFrom(caught, "资料保存失败");
  } finally {
    busy.value = false;
  }
}

async function resendVerification(): Promise<void> {
  clearFeedback();
  busy.value = true;
  try {
    const response = await auth.resendVerificationEmail();
    success.value = response.message;
  } catch (caught) {
    error.value = messageFrom(caught, "验证邮件发送失败");
  } finally {
    busy.value = false;
  }
}

async function savePassword(): Promise<void> {
  clearFeedback();
  if (newPassword.value !== confirmPassword.value) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  busy.value = true;
  try {
    const grant = await auth.reauthenticate({
      purpose: "password_change",
      current_password: currentPassword.value,
      totp_code: passwordTotpCode.value || null,
    });
    await auth.changePassword({
      reauth_token: grant.reauth_token,
      new_password: newPassword.value,
    });
    currentPassword.value = "";
    newPassword.value = "";
    confirmPassword.value = "";
    passwordTotpCode.value = "";
    success.value = "密码已修改，其他登录会话已撤销";
    sessions.value = await auth.listSessions();
  } catch (caught) {
    error.value = messageFrom(caught, "密码修改失败");
  } finally {
    busy.value = false;
  }
}

async function startTotp(): Promise<void> {
  clearFeedback();
  busy.value = true;
  try {
    setup.value = await auth.beginTotpSetup();
    success.value = "TOTP 配置已生成，请在认证器中完成绑定";
  } catch (caught) {
    error.value = messageFrom(caught, "无法生成 TOTP 配置");
  } finally {
    busy.value = false;
  }
}

async function confirmTotp(): Promise<void> {
  clearFeedback();
  busy.value = true;
  try {
    await auth.confirmTotp({ code: totpCode.value });
    setup.value = null;
    totpCode.value = "";
    success.value = "TOTP 已启用";
    sessions.value = await auth.listSessions();
  } catch (caught) {
    error.value = messageFrom(caught, "TOTP 确认失败");
  } finally {
    busy.value = false;
  }
}

async function disableTotp(): Promise<void> {
  clearFeedback();
  busy.value = true;
  try {
    const grant = await auth.reauthenticate({
      purpose: "totp_disable",
      current_password: totpCurrentPassword.value,
      totp_code: totpCode.value || null,
    });
    await auth.disableTotp({ reauth_token: grant.reauth_token });
    setup.value = null;
    totpCode.value = "";
    totpCurrentPassword.value = "";
    success.value = "TOTP 已停用";
    sessions.value = await auth.listSessions();
  } catch (caught) {
    error.value = messageFrom(caught, "TOTP 停用失败");
  } finally {
    busy.value = false;
  }
}

async function revoke(id: string): Promise<void> {
  clearFeedback();
  busyId.value = id;
  try {
    await auth.revokeSession(id);
    await load();
    success.value = "会话已撤销";
  } catch (caught) {
    error.value = messageFrom(caught, "会话撤销失败");
  } finally {
    busyId.value = "";
  }
}

onMounted(load);
</script>

<template>
  <section class="mx-auto max-w-6xl space-y-6">
    <div class="space-y-2">
      <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Account security</p>
      <h1 class="text-3xl font-semibold tracking-tight text-foreground">账号与隐私中心</h1>
      <p class="max-w-2xl text-sm leading-6 text-muted-foreground">
        管理个人资料、登录凭据、双因素认证与授权会话。所有安全写操作都会留下不可变审计记录。
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

    <Tabs default-value="profile" class="space-y-4">
      <TabsList class="grid h-auto w-full grid-cols-3 sm:w-fit sm:grid-cols-none sm:flex">
        <TabsTrigger value="profile">个人资料</TabsTrigger>
        <TabsTrigger value="security">密码与 TOTP</TabsTrigger>
        <TabsTrigger value="sessions">登录会话</TabsTrigger>
      </TabsList>

      <TabsContent value="profile" class="mt-0">
        <Card>
          <CardHeader>
            <CardTitle>基础资料</CardTitle>
            <CardDescription>邮箱用于验证与找回账号，当前阶段仅开放用户名修改。</CardDescription>
          </CardHeader>
          <CardContent class="grid gap-5 sm:max-w-xl">
            <div class="space-y-2">
              <Label for="security-username">用户名</Label>
              <Input id="security-username" v-model="username" autocomplete="username" />
              <p class="text-xs text-muted-foreground">3-32 个字符，仅支持字母、数字和下划线。</p>
            </div>
            <div class="space-y-2">
              <div class="flex flex-wrap items-center gap-2">
                <Label for="security-email">邮箱</Label>
                <Badge :variant="auth.user?.email_verified ? 'default' : 'outline'">
                  {{ auth.user?.email_verified ? "已验证" : "待验证" }}
                </Badge>
              </div>
              <Input id="security-email" :model-value="auth.user?.email ?? ''" disabled />
              <p class="text-xs text-muted-foreground">邮箱变更需要单独的验证流程，暂不在本切片内修改。</p>
              <Button
                v-if="auth.user && !auth.user.email_verified"
                type="button"
                variant="outline"
                size="sm"
                :disabled="busy"
                @click="resendVerification"
              >
                重新发送验证邮件
              </Button>
            </div>
          </CardContent>
          <CardFooter>
            <Button :disabled="busy || !username" @click="saveProfile">保存资料</Button>
          </CardFooter>
        </Card>
      </TabsContent>

      <TabsContent value="security" class="mt-0 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>修改密码</CardTitle>
            <CardDescription>修改成功后，其他设备上的登录会话将立即失效。</CardDescription>
          </CardHeader>
          <CardContent class="grid gap-5 sm:max-w-xl">
            <div class="space-y-2">
              <Label for="current-password">当前密码</Label>
              <Input id="current-password" v-model="currentPassword" type="password" autocomplete="current-password" />
            </div>
            <div class="space-y-2">
              <Label for="new-password">新密码</Label>
              <Input id="new-password" v-model="newPassword" type="password" autocomplete="new-password" />
              <p class="text-xs text-muted-foreground">至少 12 个字符，并同时包含字母与数字。</p>
            </div>
            <div class="space-y-2">
              <Label for="confirm-password">确认新密码</Label>
              <Input id="confirm-password" v-model="confirmPassword" type="password" autocomplete="new-password" />
            </div>
            <div v-if="auth.user?.totp_enabled" class="space-y-2">
              <Label for="password-totp">TOTP 验证码</Label>
              <Input id="password-totp" v-model="passwordTotpCode" inputmode="numeric" autocomplete="one-time-code" placeholder="启用 TOTP 时必填" />
            </div>
          </CardContent>
          <CardFooter>
            <Button :disabled="busy || !currentPassword || !newPassword || !confirmPassword" @click="savePassword">修改密码</Button>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader>
            <div class="flex flex-wrap items-center gap-3">
              <CardTitle>双因素认证（TOTP）</CardTitle>
              <Badge :variant="auth.user?.totp_enabled ? 'default' : 'outline'">
                {{ auth.user?.totp_enabled ? "已启用" : "未启用" }}
              </Badge>
            </div>
            <CardDescription>使用认证器应用增加登录与高风险操作的保护层。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-5">
            <div v-if="setup" class="rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm">
              <p class="font-medium text-foreground">在认证器中添加此账号</p>
              <p class="mt-2 break-all font-mono text-xs text-muted-foreground">{{ setup.secret }}</p>
              <p class="mt-2 break-all text-xs text-muted-foreground">{{ setup.provisioning_uri }}</p>
            </div>
            <div v-if="auth.user?.totp_enabled" class="max-w-xl space-y-2">
              <Label for="totp-current-password">当前密码</Label>
              <Input id="totp-current-password" v-model="totpCurrentPassword" type="password" autocomplete="current-password" />
            </div>
            <div class="max-w-xl space-y-2">
              <Label for="totp-code">认证器验证码</Label>
              <Input id="totp-code" v-model="totpCode" inputmode="numeric" autocomplete="one-time-code" placeholder="输入 6 位验证码" />
            </div>
          </CardContent>
          <CardFooter class="flex flex-wrap gap-3">
            <Button v-if="!auth.user?.totp_enabled" :disabled="busy" variant="outline" @click="startTotp">生成 TOTP 配置</Button>
            <Button v-if="setup && !auth.user?.totp_enabled" :disabled="busy || totpCode.length < 6" @click="confirmTotp">确认启用</Button>
            <Button v-if="auth.user?.totp_enabled" :disabled="busy || !totpCurrentPassword || totpCode.length < 6" variant="destructive" @click="disableTotp">停用 TOTP</Button>
          </CardFooter>
        </Card>
      </TabsContent>

      <TabsContent value="sessions" class="mt-0">
        <Card>
          <CardHeader>
            <CardTitle>登录会话</CardTitle>
            <CardDescription>IP 仅显示脱敏网段；发现异常设备时请先撤销会话，再修改密码。</CardDescription>
          </CardHeader>
          <CardContent>
            <div v-if="sessions.length === 0" class="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">暂无可用会话。</div>
            <div v-else class="space-y-4">
              <div v-for="session in sessions" :key="session.id" class="rounded-xl border bg-background/45 p-4 backdrop-blur-sm">
                <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div class="min-w-0 space-y-2">
                    <div class="flex flex-wrap items-center gap-2">
                      <p class="truncate font-medium text-foreground">{{ session.user_agent || "未知设备" }}</p>
                      <Badge v-if="session.current">当前会话</Badge>
                      <Badge v-if="session.mfa_verified" variant="outline">MFA 已验证</Badge>
                    </div>
                    <p class="text-sm text-muted-foreground">IP 网段：{{ session.ip_prefix || "未知" }}</p>
                    <p class="text-xs text-muted-foreground">
                      最近活动 {{ new Date(session.last_used_at).toLocaleString() }} · 到期 {{ new Date(session.expires_at).toLocaleString() }}
                    </p>
                  </div>
                  <Button v-if="!session.current" :disabled="busyId === session.id" variant="destructive" size="sm" @click="revoke(session.id)">撤销会话</Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>

    <Separator />
    <p class="text-xs text-muted-foreground">安全变更会触发会话策略更新，并通过审计记录保留操作轨迹。</p>
  </section>
</template>
