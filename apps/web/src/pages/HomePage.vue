<script setup lang="ts">
import type {
  ArchiveFingerprint,
  ArchiveRevealResponse,
  ArchiveSearchResponse,
  ArchiveSubmissionRequest,
  ArchiveSubmissionResponse,
  CandidateFeedbackResponse,
  CandidateStatus,
  FeedbackOutcome,
} from "@password-detective/api-contract";
import { computed, ref } from "vue";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createClientId } from "@/lib/clientId";
import { apiRequest } from "../services/api";
import {
  calculateArchiveFingerprints,
  DEFAULT_MAX_ARCHIVE_SIZE_BYTES,
  normalizeManualFingerprint,
} from "../services/fingerprint";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const configuredMaxFileSize = Number(
  import.meta.env.VITE_MAX_ARCHIVE_SIZE_BYTES ?? DEFAULT_MAX_ARCHIVE_SIZE_BYTES,
);
const maxFileSizeBytes =
  Number.isSafeInteger(configuredMaxFileSize) && configuredMaxFileSize > 0
    ? configuredMaxFileSize
    : DEFAULT_MAX_ARCHIVE_SIZE_BYTES;
const selectedFile = ref<File | null>(null);
const fingerprints = ref<ArchiveFingerprint[]>([]);
const manualFingerprint = ref("");
const progress = ref(0);
const elapsedMs = ref<number | null>(null);
const calculating = ref(false);
const searching = ref(false);
const submitting = ref(false);
const revealing = ref(false);
const feedbackCandidateId = ref("");
const error = ref("");
const notice = ref("");
const searchResult = ref<ArchiveSearchResponse | null>(null);
const candidatePassword = ref("");
const authorizationConfirmed = ref(false);
const revealedPassword = ref("");
const abortController = ref<AbortController | null>(null);

const primaryFingerprint = computed(
  () => fingerprints.value.find((item) => item.algorithm === "sha256") ?? fingerprints.value[0],
);
const canSubmit = computed(
  () =>
    auth.isAuthenticated &&
    fingerprints.value.length > 0 &&
    candidatePassword.value.length > 0 &&
    authorizationConfirmed.value,
);
const hasVerifiedCandidate = computed(
  () => (searchResult.value?.archive?.status_counts.verified ?? 0) > 0,
);

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  if (!file) return;
  selectedFile.value = file;
  fingerprints.value = [];
  searchResult.value = null;
  revealedPassword.value = "";
  error.value = "";
  notice.value = "";
  progress.value = 0;
  elapsedMs.value = null;
  calculating.value = true;
  const controller = new AbortController();
  abortController.value = controller;
  try {
    const result = await calculateArchiveFingerprints(file, {
      signal: controller.signal,
      maxFileSizeBytes,
      onProgress: (state) => {
        progress.value = state.percent;
      },
    });
    fingerprints.value = result.fingerprints;
    elapsedMs.value = result.elapsedMs;
    await search();
  } catch (caught) {
    error.value =
      caught instanceof DOMException && caught.name === "AbortError"
        ? "已取消本地指纹计算"
        : caught instanceof Error
          ? caught.message
          : "本地指纹计算失败";
  } finally {
    calculating.value = false;
    abortController.value = null;
  }
}

function cancelCalculation(): void {
  abortController.value?.abort();
}

async function searchManual(): Promise<void> {
  resetMessages();
  try {
    fingerprints.value = [normalizeManualFingerprint(manualFingerprint.value)];
    selectedFile.value = null;
    elapsedMs.value = null;
    await search();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "文件指纹格式错误";
  }
}

async function search(): Promise<void> {
  const fingerprint = primaryFingerprint.value;
  if (!fingerprint) return;
  searching.value = true;
  resetMessages();
  revealedPassword.value = "";
  try {
    const params = new URLSearchParams({
      fingerprint: fingerprint.digest,
      algorithm: fingerprint.algorithm,
    });
    searchResult.value = await apiRequest<ArchiveSearchResponse>(
      `/archives/search?${params.toString()}`,
      {},
      auth.accessToken || undefined,
    );
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "查询失败";
  } finally {
    searching.value = false;
  }
}

async function submitContribution(): Promise<void> {
  if (!canSubmit.value) return;
  submitting.value = true;
  resetMessages();
  const file = selectedFile.value;
  const payload: ArchiveSubmissionRequest = {
    fingerprints: fingerprints.value,
    password: candidatePassword.value,
    authorization_confirmed: authorizationConfirmed.value,
    authorization_version: "2026-08-01",
    ...(file ? { optional_size: file.size, optional_format: archiveFormat(file.name) } : {}),
  };
  try {
    const result = await apiRequest<ArchiveSubmissionResponse>(
      "/archives/submissions",
      {
        method: "POST",
        headers: { "Idempotency-Key": `web-submission-${createClientId()}` },
        body: JSON.stringify(payload),
      },
      auth.accessToken,
    );
    candidatePassword.value = "";
    authorizationConfirmed.value = false;
    const successMessage = result.evidence_merged
      ? "已合并为该候选的新贡献证据，积分等待验证后结算。"
      : "贡献已安全保存，候选当前为待验证状态。";
    await search();
    notice.value = successMessage;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "贡献提交失败";
  } finally {
    submitting.value = false;
  }
}

async function submitFeedback(candidateId: string, outcome: FeedbackOutcome): Promise<void> {
  feedbackCandidateId.value = candidateId;
  resetMessages();
  try {
    const result = await apiRequest<CandidateFeedbackResponse>(
      `/candidates/${encodeURIComponent(candidateId)}/feedback`,
      {
        method: "POST",
        headers: { "Idempotency-Key": `web-feedback-${createClientId()}` },
        body: JSON.stringify({ outcome }),
      },
      auth.accessToken,
    );
    await search();
    notice.value = result.changed
      ? `反馈已记录（规则 ${result.snapshot.rule_version}），候选状态：${statusLabel(result.candidate_status)}。`
      : "该反馈与当前有效反馈一致，未重复写入证据历史。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "反馈提交失败";
  } finally {
    feedbackCandidateId.value = "";
  }
}

async function reveal(): Promise<void> {
  const archiveId = searchResult.value?.archive?.id;
  if (!archiveId) return;
  revealing.value = true;
  resetMessages();
  try {
    const result = await apiRequest<ArchiveRevealResponse>(
      `/archives/${encodeURIComponent(archiveId)}/reveal`,
      { method: "POST", cache: "no-store" },
      auth.accessToken,
    );
    revealedPassword.value = result.password;
    notice.value = `已记录本次揭示，今日剩余 ${result.remaining_daily_quota} 次。`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "密码揭示失败";
  } finally {
    revealing.value = false;
  }
}

async function copyRevealedPassword(): Promise<void> {
  if (!revealedPassword.value) return;
  await navigator.clipboard.writeText(revealedPassword.value);
  notice.value = "候选密码已复制到剪贴板，请使用后及时清理剪贴板。";
}

function clearRevealedPassword(): void {
  revealedPassword.value = "";
}

function resetMessages(): void {
  error.value = "";
  notice.value = "";
}

function archiveFormat(name: string): string | undefined {
  const extension = name.split(".").pop()?.toLowerCase();
  return extension && ["zip", "7z", "rar"].includes(extension) ? extension : undefined;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MiB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GiB`;
}

function statusLabel(status: CandidateStatus): string {
  return {
    pending: "待验证",
    verified: "已验证",
    rejected: "已拒绝",
    quarantined: "已隔离",
  }[status];
}
</script>

<template>
  <section class="hero compact-hero">
    <div class="panel">
      <div class="eyebrow">M2 核心查询 · 文件始终留在本地</div>
      <h1>计算压缩包指纹，精确寻找可信候选。</h1>
      <p class="lead">
        浏览器按块计算整个文件的 SHA-256 与 MD5，只向服务端发送完整指纹；
        不上传压缩包内容，也不提供猜密或暴力破解能力。
      </p>
    </div>
    <aside class="panel stack privacy-card">
      <strong>授权使用提醒</strong>
      <span>仅处理本人拥有、本人创建或已获明确授权的压缩包。</span>
      <span>匿名查询只显示匹配和状态；完整密码需要登录、配额与审计。</span>
    </aside>
  </section>

  <section class="workspace-grid">
    <article class="panel stack">
      <div>
        <span class="badge">步骤 1</span>
        <h2>本地计算文件指纹</h2>
        <p class="muted">支持大文件分块读取；计算可取消，不会一次性载入整个文件。当前建议上限 {{ formatBytes(maxFileSizeBytes) }}。</p>
      </div>
      <label class="drop-zone" :class="{ disabled: calculating }">
        <Input type="file" :disabled="calculating" @change="onFileSelected" />
        <strong>{{ selectedFile?.name ?? "选择 ZIP、7z 或其他压缩包" }}</strong>
        <span v-if="selectedFile" class="muted">{{ formatBytes(selectedFile.size) }}</span>
        <span v-else class="muted">文件内容仅由当前浏览器读取</span>
      </label>
      <div v-if="calculating" class="stack compact-stack" aria-live="polite">
        <progress :value="progress" max="100">{{ progress }}%</progress>
        <div class="actions">
          <span>{{ progress }}%</span>
          <Button class="button secondary" type="button" @click="cancelCalculation">取消</Button>
        </div>
      </div>
      <p v-if="elapsedMs !== null" class="success">
        本地计算完成，用时 {{ elapsedMs }} ms。文件内容未上传。
      </p>

      <div class="divider"><span>或手工输入完整指纹</span></div>
      <div class="field">
        <label for="manual-fingerprint">MD5 / SHA-1 / SHA-256 / SHA-512</label>
        <Textarea
          id="manual-fingerprint"
          v-model="manualFingerprint"
          rows="3"
          placeholder="粘贴完整十六进制文件指纹"
          @keydown.ctrl.enter="searchManual"
        />
      </div>
      <Button class="button" type="button" :disabled="searching" @click="searchManual">
        {{ searching ? "查询中…" : "识别并精确查询" }}
      </Button>
    </article>

    <article class="panel stack" aria-live="polite">
      <div>
        <span class="badge">步骤 2</span>
        <h2>精确查询结果</h2>
      </div>
      <p v-if="!primaryFingerprint" class="empty-state">选择文件或输入完整指纹后开始查询。</p>
      <template v-else>
        <div class="fingerprint-list">
          <div v-for="item in fingerprints" :key="item.algorithm" class="fingerprint-row">
            <strong>{{ item.algorithm.toUpperCase() }}</strong>
            <code>{{ item.digest }}</code>
          </div>
        </div>
        <p v-if="searching" class="muted">正在检查精确匹配…</p>
        <template v-else-if="searchResult">
          <div v-if="!searchResult.matched" class="empty-state">
            <strong>暂无社区匹配</strong>
            <span>你可以在本地确认密码有效后，提交一条待验证贡献。</span>
          </div>
          <div v-else-if="searchResult.archive" class="stack compact-stack">
            <div class="result-heading">
              <span class="status-dot" aria-hidden="true"></span>
              <strong>发现 {{ searchResult.archive.candidate_count }} 条可见候选</strong>
            </div>
            <div class="actions">
              <span class="badge">
                已验证 {{ searchResult.archive.status_counts.verified ?? 0 }}
              </span>
              <span class="badge">
                待验证 {{ searchResult.archive.status_counts.pending ?? 0 }}
              </span>
              <span v-if="searchResult.archive.optional_format" class="badge">
                {{ searchResult.archive.optional_format.toUpperCase() }}
              </span>
            </div>
            <template v-if="auth.isAuthenticated">
              <div
                v-for="candidate in searchResult.archive.candidates"
                :key="candidate.id"
                class="candidate-card"
              >
                <div>
                  <strong>{{ candidate.masked_secret }}</strong>
                  <span class="status-text">{{ statusLabel(candidate.status) }}</span>
                </div>
                <small>
                  贡献 {{ candidate.submission_count }} 条 · 独立成功
                  {{ candidate.success_evidence_count }} 条 · 独立失败
                  {{ candidate.failure_evidence_count }} 条
                </small>
                <div class="actions">
                  <Button
                    class="button secondary"
                    type="button"
                    :disabled="Boolean(feedbackCandidateId)"
                    :aria-pressed="candidate.my_feedback === 'success'"
                    @click="submitFeedback(candidate.id, 'success')"
                  >
                    {{
                      feedbackCandidateId === candidate.id
                        ? "记录中…"
                        : candidate.my_feedback === "success"
                          ? "已反馈成功"
                          : "本地验证成功"
                    }}
                  </Button>
                  <Button
                    class="button secondary"
                    type="button"
                    :disabled="Boolean(feedbackCandidateId)"
                    :aria-pressed="candidate.my_feedback === 'failure'"
                    @click="submitFeedback(candidate.id, 'failure')"
                  >
                    {{ candidate.my_feedback === "failure" ? "已反馈失败" : "本地验证失败" }}
                  </Button>
                  <RouterLink
                    class="button secondary"
                    :to="{ path: '/trust-cases', query: { kind: 'report', candidate_id: candidate.id } }"
                  >
                    举报候选
                  </RouterLink>
                </div>
                <small class="muted">同一账号仅保留一条有效反馈，修改会追加历史事件。</small>
              </div>
              <Button
                v-if="hasVerifiedCandidate"
                class="button"
                type="button"
                :disabled="revealing"
                @click="reveal"
              >
                {{ revealing ? "安全揭示中…" : "揭示最高可信候选" }}
              </Button>
              <p v-else class="muted">候选尚未满足独立验证门槛，暂不可揭示。</p>
            </template>
            <div v-else class="empty-state">
              <span>登录后可查看遮挡候选，并在配额允许时揭示已验证密码。</span>
              <RouterLink class="button" to="/login">登录继续</RouterLink>
            </div>
          </div>
        </template>
      </template>

      <div v-if="revealedPassword" class="reveal-box">
        <span>本次揭示结果</span>
        <code>{{ revealedPassword }}</code>
        <div class="actions">
          <Button class="button" type="button" @click="copyRevealedPassword">复制</Button>
          <Button class="button secondary" type="button" @click="clearRevealedPassword">
            从页面清除
          </Button>
        </div>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="notice" class="success">{{ notice }}</p>
    </article>
  </section>

  <section v-if="searchResult && !searchResult.matched" class="panel contribution-panel stack">
    <div>
      <span class="badge">步骤 3</span>
      <h2>贡献已在本地验证的解压密码</h2>
      <p class="muted">
        密码将通过服务端认证加密保存；数据库仅使用密钥化标签去重，不建立明文索引。
      </p>
    </div>
    <template v-if="auth.isAuthenticated">
      <div class="field">
        <label for="candidate-password">解压密码</label>
        <Input
          id="candidate-password"
          v-model="candidatePassword"
          type="password"
          autocomplete="off"
          maxlength="512"
        />
      </div>
      <label class="authorization-check">
        <Checkbox v-model="authorizationConfirmed" />
        <span>我确认自己拥有该压缩包，或已获明确授权进行恢复和贡献。</span>
      </label>
      <Button class="button" type="button" :disabled="!canSubmit || submitting" @click="submitContribution">
        {{ submitting ? "提交中…" : "提交待验证贡献" }}
      </Button>
    </template>
    <div v-else class="empty-state">
      <span>贡献需要登录，以记录授权声明、证据来源和待结算积分。</span>
      <RouterLink class="button" to="/login">登录后贡献</RouterLink>
    </div>
  </section>
</template>
