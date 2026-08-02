<script setup lang="ts">
import type {
  DesktopCodeSignatureStatus,
  DesktopRelease,
  DesktopReleaseChannel,
  DesktopArchitecture,
} from "@password-detective/api-contract";
import { computed, onMounted, reactive, ref } from "vue";
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
  <section class="stack">
    <div class="panel release-heading">
      <div>
        <div class="eyebrow">M3 · 受控发布</div>
        <h1>桌面版本发布</h1>
        <p class="lead">创建不可变版本元数据、上传制品，并在复核摘要和签名记录后发布到稳定或测试通道。</p>
      </div>
      <div class="release-warning">
        <strong>安全边界</strong>
        <span>页面不会替代 Authenticode 验签。SHA-256 和签名者信息必须来自受控发布流水线。</span>
      </div>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="success" class="success" role="status">{{ success }}</p>

    <div class="release-layout">
      <form class="panel stack" @submit.prevent="createAndUpload">
        <div>
          <div class="eyebrow">步骤 1</div>
          <h2>创建草稿并上传制品</h2>
        </div>

        <div class="form-grid">
          <div class="field">
            <label for="release-channel">发布通道</label>
            <select id="release-channel" v-model="draft.channel">
              <option value="stable">stable · 稳定</option>
              <option value="beta">beta · 测试</option>
            </select>
          </div>
          <div class="field">
            <label for="release-architecture">架构</label>
            <select id="release-architecture" v-model="draft.architecture">
              <option value="x64">Windows x64</option>
              <option value="arm64">Windows arm64</option>
            </select>
          </div>
          <div class="field">
            <label for="release-version">发布版本</label>
            <input id="release-version" v-model="draft.version" placeholder="1.2.3" maxlength="32" required />
          </div>
          <div class="field">
            <label for="minimum-version">最低受支持版本</label>
            <input id="minimum-version" v-model="draft.minimumSupportedVersion" placeholder="1.0.0" maxlength="32" required />
          </div>
        </div>

        <label class="release-checkbox">
          <input v-model="draft.mandatory" type="checkbox" />
          <span><strong>强制升级</strong><small>客户端版本低于最低支持版本时，后端仍会自动标记为强制升级。</small></span>
        </label>

        <div class="field">
          <label for="release-notes">发布说明</label>
          <textarea id="release-notes" v-model="draft.releaseNotes" rows="5" maxlength="20000" placeholder="仅填写面向用户的合成发布说明，不包含密钥或内部路径。" />
        </div>

        <div class="field">
          <label for="artifact-file">升级制品</label>
          <input :key="artifactInputKey" id="artifact-file" type="file" accept=".msix,.msixbundle,.exe" required @change="onArtifactSelected" />
          <small v-if="artifact" class="muted">{{ artifact.name }} · {{ formatArtifactSize(artifact.size) }}</small>
        </div>

        <div class="field">
          <label for="artifact-sha256">制品 SHA-256</label>
          <input id="artifact-sha256" v-model="draft.artifactSha256" class="monospace" minlength="64" maxlength="64" autocomplete="off" spellcheck="false" required />
          <small class="muted">上传时和发布前均由后端重新计算；不要从聊天记录或非受控来源复制摘要。</small>
        </div>

        <div class="field">
          <label for="signature-status">代码签名记录</label>
          <select id="signature-status" v-model="draft.codeSignatureStatus">
            <option value="unsigned">unsigned · 未签名</option>
            <option value="test_signed">test_signed · 测试签名</option>
            <option value="verified">verified · 发布流水线已验签</option>
          </select>
        </div>

        <div v-if="draft.codeSignatureStatus === 'verified'" class="form-grid signature-fields">
          <div class="field">
            <label for="signer-subject">签名者 Subject</label>
            <input id="signer-subject" v-model="draft.signerSubject" maxlength="255" required />
          </div>
          <div class="field">
            <label for="signer-thumbprint">证书指纹</label>
            <input id="signer-thumbprint" v-model="draft.signerThumbprint" class="monospace" maxlength="128" autocomplete="off" spellcheck="false" required />
          </div>
        </div>

        <button class="button" :disabled="Boolean(activeAction)">
          {{ activeAction === "create" ? "创建并上传中…" : "创建草稿并上传" }}
        </button>
      </form>

      <aside class="panel stack">
        <div>
          <div class="eyebrow">上传恢复</div>
          <h2>草稿制品重试</h2>
        </div>
        <p class="muted">创建成功但网络中断时，可为现有草稿重新选择同名、同大小制品。后端仍会验证 SHA-256。</p>
        <div v-if="draftReleases.length" class="stack compact-stack">
          <article v-for="release in draftReleases" :key="release.id" class="retry-card">
            <strong>{{ release.version }} · {{ release.channel }}/{{ release.architecture }}</strong>
            <span class="muted">{{ release.artifact_filename }} · {{ formatArtifactSize(release.artifact_size_bytes) }}</span>
            <input type="file" accept=".msix,.msixbundle,.exe" @change="onRetryArtifactSelected(release.id, $event)" />
            <button class="button secondary" type="button" :disabled="Boolean(activeAction) || !retryArtifacts[release.id]" @click="retryUpload(release)">
              {{ activeAction === `upload:${release.id}` ? "上传中…" : "重新上传制品" }}
            </button>
          </article>
        </div>
        <div v-else class="empty-state">当前没有草稿发布记录。</div>
      </aside>
    </div>

    <section class="panel stack">
      <div class="release-list-heading">
        <div><div class="eyebrow">步骤 2</div><h2>复核并发布</h2></div>
        <button class="button secondary" type="button" :disabled="loading || Boolean(activeAction)" @click="refreshReleases()">
          {{ loading ? "刷新中…" : "刷新列表" }}
        </button>
      </div>

      <div v-if="loading && releases.length === 0" class="empty-state">正在读取发布记录…</div>
      <div v-else-if="releases.length === 0" class="empty-state">还没有桌面发布记录。</div>
      <div v-else class="release-list">
        <article v-for="release in releases" :key="release.id" class="release-card">
          <div class="release-card-title">
            <div>
              <span class="badge" :data-status="release.status">{{ statusLabel(release.status) }}</span>
              <h3>{{ release.version }} · {{ release.channel }}/{{ release.architecture }}</h3>
            </div>
            <strong v-if="release.mandatory" class="mandatory-label">强制升级</strong>
          </div>

          <dl class="release-metadata">
            <div><dt>制品</dt><dd>{{ release.artifact_filename }} · {{ formatArtifactSize(release.artifact_size_bytes) }}</dd></div>
            <div><dt>SHA-256</dt><dd><code>{{ release.artifact_sha256 }}</code></dd></div>
            <div><dt>最低版本</dt><dd>{{ release.minimum_supported_version }}</dd></div>
            <div><dt>签名记录</dt><dd>{{ signatureLabel(release.code_signature_status) }}</dd></div>
            <div><dt>制品状态</dt><dd>{{ release.artifact_uploaded ? "已上传" : "未上传" }}</dd></div>
            <div><dt>下载次数</dt><dd>{{ release.download_count }}</dd></div>
            <div><dt>创建时间</dt><dd>{{ formatTime(release.created_at) }}</dd></div>
            <div><dt>发布时间</dt><dd>{{ formatTime(release.published_at) }}</dd></div>
          </dl>

          <p v-if="release.release_notes" class="release-notes">{{ release.release_notes }}</p>
          <div class="actions">
            <button v-if="release.status === 'draft'" class="button" type="button" :disabled="Boolean(activeAction) || !release.artifact_uploaded" @click="publish(release)">
              {{ activeAction === `publish:${release.id}` ? "发布中…" : "发布版本" }}
            </button>
            <button v-if="release.status === 'published'" class="button danger" type="button" :disabled="Boolean(activeAction)" @click="withdraw(release)">
              {{ activeAction === `withdraw:${release.id}` ? "撤回中…" : "撤回版本" }}
            </button>
            <span v-if="release.status === 'draft' && !release.artifact_uploaded" class="muted">上传制品后才能发布。</span>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.release-heading { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(260px, .6fr); gap: 24px; align-items: center; }
.release-warning { display: grid; gap: 8px; padding: 18px; border-radius: 14px; border: 1px solid #fed7aa; background: #fff7ed; color: #7c2d12; }
.release-layout { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(300px, .55fr); gap: 20px; align-items: start; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.field select, .field input { box-sizing: border-box; }
.field select { width: 100%; border: 1px solid var(--border); border-radius: 11px; padding: 12px 14px; background: white; }
.field small { line-height: 1.55; }
.release-checkbox { display: flex; gap: 10px; align-items: flex-start; padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: #f8fafc; }
.release-checkbox input { margin-top: 4px; }
.release-checkbox span { display: grid; gap: 4px; }
.release-checkbox small { color: var(--muted); }
.monospace { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.signature-fields { padding: 16px; border-radius: 12px; background: #fff7ed; border: 1px solid #fed7aa; }
.retry-card { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: #f8fafc; }
.retry-card input { max-width: 100%; }
.release-list-heading, .release-card-title { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.release-list { display: grid; gap: 16px; }
.release-card { display: grid; gap: 16px; padding: 20px; border: 1px solid var(--border); border-radius: 16px; background: #fbfdff; }
.release-card h3 { margin: 10px 0 0; }
.badge[data-status="published"] { color: #067647; background: #ecfdf3; }
.badge[data-status="withdrawn"] { color: #b42318; background: #fff1f0; }
.mandatory-label { color: #b42318; }
.release-metadata { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 20px; margin: 0; }
.release-metadata div { min-width: 0; }
.release-metadata dt { color: var(--muted); font-size: 12px; font-weight: 700; }
.release-metadata dd { margin: 4px 0 0; overflow-wrap: anywhere; }
.release-metadata code { font-size: 12px; }
.release-notes { margin: 0; padding: 14px; white-space: pre-wrap; border-radius: 12px; background: white; border: 1px solid var(--border); }
@media (max-width: 960px) {
  .release-heading, .release-layout { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .form-grid, .release-metadata { grid-template-columns: 1fr; }
  .release-list-heading, .release-card-title { flex-direction: column; }
}
</style>
