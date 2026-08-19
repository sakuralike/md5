<script setup lang="ts">
import { ApiError, type RegistrationInvite, type RegistrationMode } from "@password-detective/api-contract";
import { Clipboard, KeyRound, RefreshCw, Save, ShieldCheck, XCircle } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  createRegistrationInvite,
  getRegistrationPolicy,
  listRegistrationInvites,
  revokeRegistrationInvite,
  saveRegistrationPolicy,
} from "../services/registration";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const mode = ref<RegistrationMode>("open");
const invites = ref<RegistrationInvite[]>([]);
const loading = ref(false);
const saving = ref(false);
const creating = ref(false);
const error = ref("");
const notice = ref("");
const label = ref("");
const maxUses = ref(1);
const expiresAt = ref("");
const createdCode = ref("");

function describeError(value: unknown): string {
  if (value instanceof ApiError) return value.body.message;
  return value instanceof Error ? value.message : "注册治理服务暂时不可用";
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [policy, inviteList] = await Promise.all([
      getRegistrationPolicy(auth.accessToken),
      listRegistrationInvites(auth.accessToken),
    ]);
    mode.value = policy.mode;
    invites.value = inviteList.items;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function savePolicy(): Promise<void> {
  saving.value = true;
  error.value = "";
  notice.value = "";
  try {
    mode.value = (await saveRegistrationPolicy(mode.value, auth.accessToken)).mode;
    notice.value = mode.value === "open" ? "已开放注册。" : "已切换为邀请码注册。";
  } catch (value) {
    error.value = describeError(value);
  } finally {
    saving.value = false;
  }
}

async function createInvite(): Promise<void> {
  creating.value = true;
  error.value = "";
  notice.value = "";
  createdCode.value = "";
  try {
    const created = await createRegistrationInvite(
      {
        label: label.value.trim(),
        maxUses: maxUses.value,
        ...(expiresAt.value ? { expiresAt: new Date(expiresAt.value).toISOString() } : {}),
      },
      auth.accessToken,
    );
    createdCode.value = created.code;
    label.value = "";
    maxUses.value = 1;
    expiresAt.value = "";
    await load();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    creating.value = false;
  }
}

async function revoke(invite: RegistrationInvite): Promise<void> {
  error.value = "";
  try {
    const updated = await revokeRegistrationInvite(invite.id, auth.accessToken);
    invites.value = invites.value.map((item) => (item.id === updated.id ? updated : item));
  } catch (value) {
    error.value = describeError(value);
  }
}

async function copyCode(): Promise<void> {
  await navigator.clipboard.writeText(createdCode.value);
  notice.value = "邀请码已复制。关闭提示后后台不会再次显示明文。";
}

function formatDate(value: string | null): string {
  if (!value) return "永不过期";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

const statusLabels = { active: "可用", exhausted: "已用尽", expired: "已过期", revoked: "已撤销" } as const;

onMounted(() => void load());
</script>

<template>
  <section id="registration-governance" class="space-y-5 rounded-lg border bg-card p-5 text-card-foreground shadow-sm">
    <header class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
      <div class="flex items-start gap-3">
        <span class="rounded-md bg-primary/10 p-2 text-primary"><KeyRound class="h-5 w-5" /></span>
        <div>
          <h2 class="font-semibold">注册策略与邀请码</h2>
          <p class="mt-1 text-sm leading-6 text-muted-foreground">开放注册与邀请码注册互斥；邀请码明文仅在创建成功后显示一次。</p>
        </div>
      </div>
      <Button variant="outline" size="sm" :disabled="loading" @click="load">
        <RefreshCw class="mr-2 h-4 w-4" :class="loading && 'animate-spin'" />刷新
      </Button>
    </header>

    <div class="grid gap-4 border-y py-5 md:grid-cols-[minmax(0,20rem)_auto] md:items-end">
      <div class="space-y-2">
        <Label>注册模式</Label>
        <Select v-model="mode">
          <SelectTrigger aria-label="注册模式"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="open">开放注册</SelectItem>
            <SelectItem value="invite_only">仅邀请码注册</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button class="md:justify-self-start" :disabled="saving" @click="savePolicy">
        <Save class="mr-2 h-4 w-4" />{{ saving ? "保存中" : "保存注册策略" }}
      </Button>
    </div>

    <p v-if="error" class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{{ error }}</p>
    <p v-if="notice" class="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary" role="status">{{ notice }}</p>
    <div v-if="createdCode" class="space-y-3 rounded-md border border-primary/30 bg-primary/5 p-4" role="status">
      <div class="flex items-center gap-2 font-medium"><ShieldCheck class="h-4 w-4" />一次性邀请码明文</div>
      <code class="block break-all text-sm">{{ createdCode }}</code>
      <Button size="sm" variant="outline" @click="copyCode"><Clipboard class="mr-2 h-4 w-4" />复制邀请码</Button>
    </div>

    <form class="grid gap-4 md:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_10rem_15rem_auto] xl:items-end" @submit.prevent="createInvite">
      <div class="space-y-2">
        <Label for="invite-label">用途名称</Label>
        <Input id="invite-label" v-model="label" maxlength="64" required placeholder="例如：社区内测第 2 批" />
      </div>
      <div class="space-y-2">
        <Label for="invite-max-uses">可用次数</Label>
        <Input id="invite-max-uses" v-model.number="maxUses" type="number" min="1" max="10000" required />
      </div>
      <div class="space-y-2">
        <Label for="invite-expiry">过期时间（可选）</Label>
        <Input id="invite-expiry" v-model="expiresAt" type="datetime-local" />
      </div>
      <Button type="submit" :disabled="creating"><KeyRound class="mr-2 h-4 w-4" />{{ creating ? "生成中" : "生成邀请码" }}</Button>
    </form>

    <div class="overflow-hidden rounded-lg border">
      <Table>
        <TableHeader><TableRow><TableHead>用途</TableHead><TableHead>状态</TableHead><TableHead>使用量</TableHead><TableHead>有效期</TableHead><TableHead class="text-right">操作</TableHead></TableRow></TableHeader>
        <TableBody>
          <TableEmpty v-if="!loading && invites.length === 0" :colspan="5">暂无邀请码</TableEmpty>
          <TableRow v-for="invite in invites" :key="invite.id">
            <TableCell class="font-medium">{{ invite.label }}</TableCell>
            <TableCell><Badge :variant="invite.status === 'active' ? 'default' : 'secondary'">{{ statusLabels[invite.status] }}</Badge></TableCell>
            <TableCell>{{ invite.use_count }} / {{ invite.max_uses }}</TableCell>
            <TableCell>{{ formatDate(invite.expires_at) }}</TableCell>
            <TableCell class="text-right">
              <Button v-if="invite.status === 'active'" size="sm" variant="outline" @click="revoke(invite)"><XCircle class="mr-2 h-4 w-4" />撤销</Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </section>
</template>
