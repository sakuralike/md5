<script setup lang="ts">
import type {
  DesktopCodeSignatureStatus,
  DesktopRelease,
  DesktopReleaseChannel,
  DesktopArchitecture,
} from "@password-detective/api-contract";
import { computed, onMounted, reactive, ref } from "vue";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Checkbox } from "../components/ui/checkbox";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import {
  buildDesktopReleasePayload,
  createDesktopRelease,
  formatArtifactSize,
  listDesktopReleases,
  publishDesktopRelease,
  uploadDesktopReleaseArtifact,
  validateArtifactForRelease,
  withdrawDesktopRelease,
} from "../services/desktopReleases";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const releases = ref<DesktopRelease[]>([]);
const loading = ref(false);
const activeAction = ref("");
const error = ref("");
const success = ref("");
const artifact = ref<File | null>(null);
const artifactInputKey = ref(0);
const retryArtifacts = reactive<Record<string, File | undefined>>({});

const draft = reactive({
  channel: "stable" as DesktopReleaseChannel,
  architecture: "x64" as DesktopArchitecture,
  version: "",
  minimumSupportedVersion: "",
  mandatory: false,
  releaseNotes: "",
  artifactSha256: "",
  codeSignatureStatus: "unsigned" as DesktopCodeSignatureStatus,
  signerSubject: "",
  signerThumbprint: "",
});

const draftReleases = computed(() => releases.value.filter((release) => release.status === "draft"));

function clearMessages(): void {
  error.value = "";
  success.value = "";
}

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

async function refreshReleases(showError = true): Promise<void> {
  loading.value = true;
  if (showError) error.value = "";
  try {
    releases.value = await listDesktopReleases(auth.accessToken);
  } catch (caught) {
    if (showError) error.value = errorMessage(caught, "无法读取桌面发布记录");
  } finally {
    loading.value = false;
  }
}

function onArtifactSelected(event: Event): void {
  artifact.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

function onRetryArtifactSelected(releaseId: string, event: Event): void {
  retryArtifacts[releaseId] = (event.target as HTMLInputElement).files?.[0];
}

function resetDraft(): void {
  draft.version = "";
  draft.minimumSupportedVersion = "";
  draft.mandatory = false;
  draft.releaseNotes = "";
  draft.artifactSha256 = "";
  draft.codeSignatureStatus = "unsigned";
  draft.signerSubject = "";
  draft.signerThumbprint = "";
  artifact.value = null;
  artifactInputKey.value += 1;
}

async function createAndUpload(): Promise<void> {
  clearMessages();
  if (!artifact.value) {
    error.value = "请选择升级制品";
    return;
  }

  let created: DesktopRelease | null = null;
  activeAction.value = "create";
  try {
    const payload = buildDesktopReleasePayload(draft, artifact.value);
    created = await createDesktopRelease(payload, auth.accessToken);
    await uploadDesktopReleaseArtifact(created.id, artifact.value, auth.accessToken);
    success.value = `版本 ${created.version} 草稿及制品上传完成，请复核后发布。`;
    resetDraft();
  } catch (caught) {
    const prefix = created ? `草稿 ${created.version} 已创建，但制品上传失败：` : "创建发布草稿失败：";
    error.value = `${prefix}${errorMessage(caught, "未知错误")}`;
  } finally {
    activeAction.value = "";
    await refreshReleases(false);
  }
}

async function retryUpload(release: DesktopRelease): Promise<void> {
  clearMessages();
  const selected = retryArtifacts[release.id];
  if (!selected) {
    error.value = "请先选择与发布记录匹配的升级制品";
    return;
  }
  activeAction.value = `upload:${release.id}`;
  try {
    validateArtifactForRelease(release, selected);
    await uploadDesktopReleaseArtifact(release.id, selected, auth.accessToken);
    delete retryArtifacts[release.id];
    success.value = `版本 ${release.version} 的制品上传完成。`;
  } catch (caught) {
    error.value = errorMessage(caught, "制品上传失败");
  } finally {
    activeAction.value = "";
    await refreshReleases(false);
  }
}

async function publish(release: DesktopRelease): Promise<void> {
  clearMessages();
  if (!globalThis.confirm(`确认发布 ${release.channel}/${release.architecture} ${release.version}？发布后元数据不可修改。`)) return;
  activeAction.value = `publish:${release.id}`;
  try {
    await publishDesktopRelease(release.id, auth.accessToken);
    success.value = `版本 ${release.version} 已发布。`;
  } catch (caught) {
    error.value = errorMessage(caught, "发布失败");
  } finally {
    activeAction.value = "";
    await refreshReleases(false);
  }
}

async function withdraw(release: DesktopRelease): Promise<void> {
  clearMessages();
  if (!globalThis.confirm(`确认撤回 ${release.channel}/${release.architecture} ${release.version}？客户端将不能继续下载。`)) return;
  activeAction.value = `withdraw:${release.id}`;
  try {
    await withdrawDesktopRelease(release.id, auth.accessToken);
    success.value = `版本 ${release.version} 已撤回。`;
  } catch (caught) {
    error.value = errorMessage(caught, "撤回失败");
  } finally {
    activeAction.value = "";
    await refreshReleases(false);
  }
}

function statusLabel(status: DesktopRelease["status"]): string {
  return { draft: "草稿", published: "已发布", withdrawn: "已撤回" }[status];
}

function signatureLabel(status: DesktopCodeSignatureStatus): string {
  return { unsigned: "未签名", test_signed: "测试签名", verified: "签名记录已验证" }[status];
}

function releaseStatusVariant(
  status: DesktopRelease["status"],
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "published") return "secondary";
  if (status === "withdrawn") return "destructive";
  return "outline";
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

onMounted(() => refreshReleases());
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">M3 · 受控发布</p>
        <h1 class="text-2xl font-semibold tracking-tight">桌面版本发布</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          创建不可变版本元数据、上传制品，并在复核摘要和签名记录后发布到稳定或测试通道。
        </p>
      </div>
      <aside class="max-w-md space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm">
        <strong class="text-destructive">安全边界</strong>
        <p class="leading-6 text-muted-foreground">
          页面不会替代 Authenticode 验签。SHA-256 和签名者信息必须来自受控发布流水线。
        </p>
      </aside>
    </header>

    <p
      v-if="error"
      class="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="success"
      class="rounded-md border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-primary"
      role="status"
    >
      {{ success }}
    </p>

    <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(18.75rem,0.55fr)]">
      <form
        class="space-y-5 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6"
        @submit.prevent="createAndUpload"
      >
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">步骤 1</p>
          <h2 class="text-lg font-semibold tracking-tight">创建草稿并上传制品</h2>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <Label class="grid gap-2">
            发布通道
            <Select v-model="draft.channel">
              <SelectTrigger id="release-channel"><SelectValue placeholder="选择发布通道" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="stable">stable · 稳定</SelectItem>
                <SelectItem value="beta">beta · 测试</SelectItem>
              </SelectContent>
            </Select>
          </Label>
          <Label class="grid gap-2">
            架构
            <Select v-model="draft.architecture">
              <SelectTrigger id="release-architecture"><SelectValue placeholder="选择架构" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="x64">Windows x64</SelectItem>
                <SelectItem value="arm64">Windows arm64</SelectItem>
              </SelectContent>
            </Select>
          </Label>
          <Label class="grid gap-2">
            发布版本
            <Input id="release-version" v-model="draft.version" placeholder="1.2.3" maxlength="32" required />
          </Label>
          <Label class="grid gap-2">
            最低受支持版本
            <Input
              id="minimum-version"
              v-model="draft.minimumSupportedVersion"
              placeholder="1.0.0"
              maxlength="32"
              required
            />
          </Label>
        </div>

        <Label class="flex items-start gap-3 rounded-lg border bg-muted/40 p-4">
          <Checkbox v-model="draft.mandatory" class="mt-0.5" />
          <span class="grid gap-1">
            <strong>强制升级</strong>
            <small class="leading-5 text-muted-foreground">
              客户端版本低于最低支持版本时，后端仍会自动标记为强制升级。
            </small>
          </span>
        </Label>

        <Label class="grid gap-2">
          发布说明
          <Textarea
            id="release-notes"
            v-model="draft.releaseNotes"
            rows="5"
            maxlength="20000"
            placeholder="仅填写面向用户的合成发布说明，不包含密钥或内部路径。"
          />
        </Label>

        <Label class="grid gap-2">
          升级制品
          <Input
            :key="artifactInputKey"
            id="artifact-file"
            type="file"
            accept=".msix,.msixbundle,.exe"
            required
            @change="onArtifactSelected"
          />
          <small v-if="artifact" class="text-muted-foreground">
            {{ artifact.name }} · {{ formatArtifactSize(artifact.size) }}
          </small>
        </Label>

        <Label class="grid gap-2">
          制品 SHA-256
          <Input
            id="artifact-sha256"
            v-model="draft.artifactSha256"
            class="font-mono"
            minlength="64"
            maxlength="64"
            autocomplete="off"
            spellcheck="false"
            required
          />
          <small class="leading-5 text-muted-foreground">
            上传时和发布前均由后端重新计算；不要从聊天记录或非受控来源复制摘要。
          </small>
        </Label>

        <Label class="grid gap-2">
          代码签名记录
          <Select v-model="draft.codeSignatureStatus">
            <SelectTrigger id="signature-status"><SelectValue placeholder="选择签名状态" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="unsigned">unsigned · 未签名</SelectItem>
              <SelectItem value="test_signed">test_signed · 测试签名</SelectItem>
              <SelectItem value="verified">verified · 发布流水线已验签</SelectItem>
            </SelectContent>
          </Select>
        </Label>

        <div
          v-if="draft.codeSignatureStatus === 'verified'"
          class="grid gap-4 rounded-lg border border-primary/20 bg-primary/5 p-4 sm:grid-cols-2"
        >
          <Label class="grid gap-2">
            签名者 Subject
            <Input id="signer-subject" v-model="draft.signerSubject" maxlength="255" required />
          </Label>
          <Label class="grid gap-2">
            证书指纹
            <Input
              id="signer-thumbprint"
              v-model="draft.signerThumbprint"
              class="font-mono"
              maxlength="128"
              autocomplete="off"
              spellcheck="false"
              required
            />
          </Label>
        </div>

        <Button type="submit" :disabled="Boolean(activeAction)">
          {{ activeAction === "create" ? "创建并上传中…" : "创建草稿并上传" }}
        </Button>
      </form>

      <aside class="space-y-4 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6 xl:sticky xl:top-4">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">上传恢复</p>
          <h2 class="text-lg font-semibold tracking-tight">草稿制品重试</h2>
        </div>
        <p class="text-sm leading-6 text-muted-foreground">
          创建成功但网络中断时，可为现有草稿重新选择同名、同大小制品。后端仍会验证 SHA-256。
        </p>
        <div v-if="draftReleases.length" class="space-y-3">
          <article
            v-for="release in draftReleases"
            :key="release.id"
            class="space-y-3 rounded-lg border bg-muted/30 p-4"
          >
            <strong class="block">{{ release.version }} · {{ release.channel }}/{{ release.architecture }}</strong>
            <span class="block break-all text-sm text-muted-foreground">
              {{ release.artifact_filename }} · {{ formatArtifactSize(release.artifact_size_bytes) }}
            </span>
            <Input
              type="file"
              accept=".msix,.msixbundle,.exe"
              @change="onRetryArtifactSelected(release.id, $event)"
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              :disabled="Boolean(activeAction) || !retryArtifacts[release.id]"
              @click="retryUpload(release)"
            >
              {{ activeAction === `upload:${release.id}` ? "上传中…" : "重新上传制品" }}
            </Button>
          </article>
        </div>
        <p v-else class="rounded-md bg-muted px-4 py-8 text-center text-sm text-muted-foreground">
          当前没有草稿发布记录。
        </p>
      </aside>
    </div>

    <section class="space-y-5 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">步骤 2</p>
          <h2 class="text-lg font-semibold tracking-tight">复核并发布</h2>
        </div>
        <Button type="button" variant="secondary" :disabled="loading || Boolean(activeAction)" @click="refreshReleases()">
          {{ loading ? "刷新中…" : "刷新列表" }}
        </Button>
      </div>

      <p v-if="loading && releases.length === 0" class="py-8 text-center text-sm text-muted-foreground">
        正在读取发布记录…
      </p>
      <p v-else-if="releases.length === 0" class="py-8 text-center text-sm text-muted-foreground">
        还没有桌面发布记录。
      </p>
      <div v-else class="space-y-4">
        <article
          v-for="release in releases"
          :key="release.id"
          class="space-y-5 rounded-lg border bg-muted/20 p-4 sm:p-5"
        >
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="space-y-2">
              <Badge :variant="releaseStatusVariant(release.status)">{{ statusLabel(release.status) }}</Badge>
              <h3 class="text-lg font-semibold tracking-tight">
                {{ release.version }} · {{ release.channel }}/{{ release.architecture }}
              </h3>
            </div>
            <Badge v-if="release.mandatory" variant="destructive">强制升级</Badge>
          </div>

          <dl class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div class="min-w-0 space-y-1"><dt class="text-xs font-semibold text-muted-foreground">制品</dt><dd class="break-all text-sm">{{ release.artifact_filename }} · {{ formatArtifactSize(release.artifact_size_bytes) }}</dd></div>
            <div class="min-w-0 space-y-1"><dt class="text-xs font-semibold text-muted-foreground">SHA-256</dt><dd><code class="break-all text-xs">{{ release.artifact_sha256 }}</code></dd></div>
            <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">最低版本</dt><dd>{{ release.minimum_supported_version }}</dd></div>
            <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">签名记录</dt><dd>{{ signatureLabel(release.code_signature_status) }}</dd></div>
            <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">制品状态</dt><dd>{{ release.artifact_uploaded ? "已上传" : "未上传" }}</dd></div>
            <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">下载次数</dt><dd>{{ release.download_count }}</dd></div>
            <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">创建时间</dt><dd>{{ formatTime(release.created_at) }}</dd></div>
            <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">发布时间</dt><dd>{{ formatTime(release.published_at) }}</dd></div>
          </dl>

          <p v-if="release.release_notes" class="whitespace-pre-wrap rounded-lg border bg-background p-4 text-sm leading-6">
            {{ release.release_notes }}
          </p>
          <div class="flex flex-wrap items-center gap-2">
            <Button
              v-if="release.status === 'draft'"
              type="button"
              :disabled="Boolean(activeAction) || !release.artifact_uploaded"
              @click="publish(release)"
            >
              {{ activeAction === `publish:${release.id}` ? "发布中…" : "发布版本" }}
            </Button>
            <Button
              v-if="release.status === 'published'"
              type="button"
              variant="destructive"
              :disabled="Boolean(activeAction)"
              @click="withdraw(release)"
            >
              {{ activeAction === `withdraw:${release.id}` ? "撤回中…" : "撤回版本" }}
            </Button>
            <span v-if="release.status === 'draft' && !release.artifact_uploaded" class="text-sm text-muted-foreground">
              上传制品后才能发布。
            </span>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>
