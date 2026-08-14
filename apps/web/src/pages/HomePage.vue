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
  HomeDiscoveryResponse,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
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
import { getHomeDiscovery } from "../services/site";
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
const searchMode = ref<"file" | "manual">("file");
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
const discovery = ref<HomeDiscoveryResponse>({
  hot_hashes: [],
  contribution_leaders: [],
  points_leaders: [],
});
const discoveryLoading = ref(true);

async function loadDiscovery(): Promise<void> {
  discoveryLoading.value = true;
  try {
    discovery.value = await getHomeDiscovery();
  } catch {
    discovery.value = { hot_hashes: [], contribution_leaders: [], points_leaders: [] };
  } finally {
    discoveryLoading.value = false;
  }
}

onMounted(loadDiscovery);

const primaryFingerprint = computed(
  () => fingerprints.value.find((item) => item.algorithm === "sha256") ?? fingerprints.value[0],
);
const canSubmit = computed(
  () =>
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
      auth.accessToken || undefined,
    );
    candidatePassword.value = "";
    authorizationConfirmed.value = false;
    const confirmationMessage = `需至少 ${result.required_success_confirmations} 名不同登录用户确认正确后进入总哈希池。`;
    const successMessage = result.submitter_kind === "guest"
      ? `游客贡献已进入待验证池，${confirmationMessage}`
      : result.evidence_merged
        ? `已合并为该候选的新网页贡献，${confirmationMessage}`
        : `网页贡献已进入待验证池，${confirmationMessage}`;
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
  <section class="mx-auto flex min-w-0 w-full max-w-4xl flex-col items-center px-4 py-8 text-center sm:py-12">
    <div class="eyebrow">TRUSTED ARCHIVE LAB · LOCAL FIRST</div>
    <h1 class="mt-4 max-w-3xl bg-gradient-to-r from-primary via-accent to-primary bg-clip-text text-4xl font-extrabold tracking-tight text-transparent sm:text-5xl">
      计算压缩包指纹，精确寻找可信候选。
    </h1>
    <p class="mt-5 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
      浏览器按块计算整个文件的 SHA-256 与 MD5，只向服务端发送完整指纹；
      不上传压缩包内容，也不提供猜密或暴力破解能力。
    </p>
    <p class="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
      网页提交统一进入待验证池，至少 4 名不同登录用户确认正确后进入总哈希池。
    </p>
  </section>

  <section class="mx-auto grid min-w-0 w-full max-w-4xl gap-6 px-4" data-testid="home-search-workspace">
    <div class="flex w-full min-w-0 justify-center">
      <div class="flex w-full min-w-0 max-w-full flex-wrap justify-center rounded-full border border-border/70 bg-card/60 p-1 shadow-sm backdrop-blur-xl" role="tablist" aria-label="查询方式">
        <Button
          type="button"
          variant="ghost"
          role="tab"
          :aria-selected="searchMode === 'file'"
          :class="searchMode === 'file' ? 'rounded-full bg-background text-primary shadow-sm' : 'rounded-full text-muted-foreground'"
          @click="searchMode = 'file'"
        >
          本地文件查询
        </Button>
        <Button
          type="button"
          variant="ghost"
          role="tab"
          :aria-selected="searchMode === 'manual'"
          :class="searchMode === 'manual' ? 'rounded-full bg-background text-primary shadow-sm' : 'rounded-full text-muted-foreground'"
          @click="searchMode = 'manual'"
        >
          手工指纹查询
        </Button>
      </div>
    </div>

    <div class="min-w-0 rounded-[2rem] border border-border/70 bg-card/70 p-4 shadow-xl backdrop-blur-xl sm:p-6">
      <div v-if="searchMode === 'file'" class="grid gap-4">
        <label
          class="flex min-w-0 min-h-16 cursor-pointer items-center gap-3 rounded-full border border-dashed border-primary/40 bg-background/75 px-5 py-3 text-left transition hover:border-primary hover:bg-primary/5"
          :class="{ 'pointer-events-none opacity-60': calculating }"
        >
          <Input type="file" class="!absolute !h-px !w-px !overflow-hidden !p-0 !opacity-0" :disabled="calculating" @change="onFileSelected" />
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary" aria-hidden="true">↑</span>
          <span class="min-w-0 flex-1">
            <strong class="block truncate text-sm sm:text-base">{{ selectedFile?.name ?? "选择 ZIP、7z 或其他压缩包" }}</strong>
            <span class="mt-1 block truncate text-xs text-muted-foreground">{{ selectedFile ? formatBytes(selectedFile.size) : `文件内容仅由当前浏览器读取 · 上限 ${formatBytes(maxFileSizeBytes)}` }}</span>
          </span>
          <span class="hidden rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground sm:inline-flex">选择文件</span>
        </label>
        <div v-if="calculating" class="grid gap-2 px-3" aria-live="polite">
          <progress class="h-2 w-full accent-primary" :value="progress" max="100">{{ progress }}%</progress>
          <div class="flex items-center justify-between text-sm text-muted-foreground">
            <span>正在本地计算 {{ progress }}%</span>
            <Button variant="outline" size="sm" type="button" @click="cancelCalculation">取消</Button>
          </div>
        </div>
        <p v-if="elapsedMs !== null" class="text-sm text-emerald-600 dark:text-emerald-400">本地计算完成，用时 {{ elapsedMs }} ms。文件内容未上传。</p>
      </div>

      <div v-else class="grid gap-4">
        <label for="manual-fingerprint" class="sr-only">MD5 / SHA-1 / SHA-256 / SHA-512</label>
        <Textarea
          id="manual-fingerprint"
          v-model="manualFingerprint"
          class="min-h-28 rounded-3xl bg-background/75 px-5 py-4"
          rows="3"
          placeholder="粘贴完整十六进制文件指纹"
          @keydown.ctrl.enter="searchManual"
        />
        <p class="px-3 text-xs text-muted-foreground">支持 MD5、SHA-1、SHA-256、SHA-512；按 Ctrl + Enter 可直接查询。</p>
      </div>

      <div class="mt-5 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <Button
          v-if="searchMode === 'manual'"
          class="min-w-44 rounded-full px-6"
          type="button"
          :disabled="searching"
          @click="searchManual"
        >
          {{ searching ? "查询中…" : "识别并精确查询" }}
        </Button>
        <Button v-else-if="primaryFingerprint" variant="outline" class="rounded-full px-6" type="button" :disabled="searching" @click="search">
          {{ searching ? "查询中…" : "重新查询" }}
        </Button>
        <span class="text-xs text-muted-foreground">隐私优先 · 本地计算 · 精确匹配</span>
      </div>
    </div>
  </section>

  <section class="mx-auto mt-8 max-w-4xl px-4" aria-live="polite">
    <div class="rounded-[2rem] border border-border/70 bg-card/70 p-5 shadow-lg backdrop-blur-xl sm:p-7">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <span class="badge">查询结果</span>
          <h2 class="mt-3 text-2xl font-semibold tracking-tight">精确查询结果</h2>
        </div>
        <div class="rounded-full bg-muted/70 px-3 py-1 text-xs text-muted-foreground">服务端只接收指纹</div>
      </div>
      <p v-if="!primaryFingerprint" class="mt-6 rounded-2xl bg-muted/50 px-4 py-5 text-center text-sm text-muted-foreground">选择文件或输入完整指纹后开始查询。</p>
      <template v-else>
        <div class="mt-6 grid gap-2 rounded-2xl bg-muted/40 p-4">
          <div v-for="item in fingerprints" :key="item.algorithm" class="grid gap-1 border-b border-border/50 pb-2 last:border-0 last:pb-0 sm:grid-cols-[7rem_1fr] sm:items-center">
            <strong class="text-xs uppercase tracking-widest text-muted-foreground">{{ item.algorithm }}</strong>
            <code class="break-all text-xs text-foreground">{{ item.digest }}</code>
          </div>
        </div>
        <p v-if="searching" class="mt-5 text-sm text-muted-foreground">正在检查精确匹配…</p>
        <template v-else-if="searchResult">
          <div v-if="!searchResult.matched" class="mt-5 rounded-2xl border border-dashed border-border bg-muted/30 p-5">
            <strong class="block text-lg">暂无社区匹配</strong>
            <span class="mt-2 block text-sm text-muted-foreground">你可以在本地确认密码有效后，提交一条待验证贡献。</span>
            <Button variant="outline" size="sm" class="mt-4" as-child>
              <RouterLink :to="{ path: `/hash/${searchResult.query.algorithm}/${searchResult.query.digest}` }">打开哈希详情页</RouterLink>
            </Button>
          </div>
          <div v-else-if="searchResult.archive" class="mt-5 grid gap-4">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-sm font-semibold">发现 {{ searchResult.archive.candidate_count }} 条可见候选</span>
              <span class="badge">已验证 {{ searchResult.archive.status_counts.verified ?? 0 }}</span>
              <span class="badge">待验证 {{ searchResult.archive.status_counts.pending ?? 0 }}</span>
              <span v-if="searchResult.archive.optional_format" class="badge">{{ searchResult.archive.optional_format.toUpperCase() }}</span>
              <Button variant="ghost" size="sm" as-child>
                <RouterLink :to="{ path: `/hash/${searchResult.query.algorithm}/${searchResult.query.digest}` }">查看哈希详情</RouterLink>
              </Button>
            </div>
            <template v-if="auth.isAuthenticated">
              <div v-for="candidate in searchResult.archive.candidates" :key="candidate.id" class="rounded-2xl border border-border/70 bg-background/60 p-4">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <strong>{{ candidate.masked_secret }}</strong>
                  <span class="status-text">{{ statusLabel(candidate.status) }}</span>
                </div>
                <small class="mt-2 block text-muted-foreground">贡献 {{ candidate.submission_count }} 条 · 独立成功 {{ candidate.success_evidence_count }} 条 · 独立失败 {{ candidate.failure_evidence_count }} 条</small>
                <div class="mt-4 flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" type="button" :disabled="Boolean(feedbackCandidateId)" :aria-pressed="candidate.my_feedback === 'success'" @click="submitFeedback(candidate.id, 'success')">
                    {{ feedbackCandidateId === candidate.id ? "记录中…" : candidate.my_feedback === "success" ? "已反馈成功" : "本地验证成功" }}
                  </Button>
                  <Button variant="outline" size="sm" type="button" :disabled="Boolean(feedbackCandidateId)" :aria-pressed="candidate.my_feedback === 'failure'" @click="submitFeedback(candidate.id, 'failure')">
                    {{ candidate.my_feedback === "failure" ? "已反馈失败" : "本地验证失败" }}
                  </Button>
                  <Button variant="ghost" size="sm" as-child><RouterLink :to="{ path: '/trust-cases', query: { kind: 'report', candidate_id: candidate.id } }">举报候选</RouterLink></Button>
                </div>
                <small class="mt-3 block text-muted-foreground">同一账号仅保留一条有效反馈，修改会追加历史事件。</small>
              </div>
              <Button v-if="hasVerifiedCandidate" class="w-full rounded-full sm:w-auto" type="button" :disabled="revealing" @click="reveal">{{ revealing ? "安全揭示中…" : "揭示最高可信候选" }}</Button>
              <p v-else class="text-sm text-muted-foreground">候选尚未满足独立验证门槛，暂不可揭示。</p>
            </template>
            <div v-else class="flex flex-col gap-3 rounded-2xl bg-muted/40 p-5 sm:flex-row sm:items-center sm:justify-between">
              <span class="text-sm text-muted-foreground">登录后可查看遮挡候选，并在配额允许时揭示已验证密码。</span>
              <Button class="rounded-full" as-child><RouterLink to="/login">登录继续</RouterLink></Button>
            </div>
          </div>
        </template>
      </template>
      <div v-if="revealedPassword" class="mt-5 rounded-2xl border border-primary/30 bg-primary/5 p-4">
        <span class="text-sm text-muted-foreground">本次揭示结果</span>
        <code class="mt-2 block break-all text-lg font-semibold">{{ revealedPassword }}</code>
        <div class="mt-4 flex flex-wrap gap-2">
          <Button type="button" @click="copyRevealedPassword">复制</Button>
          <Button variant="outline" type="button" @click="clearRevealedPassword">从页面清除</Button>
        </div>
      </div>
      <p v-if="error" class="mt-4 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>
      <p v-if="notice" class="mt-4 rounded-xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-600 dark:text-emerald-400">{{ notice }}</p>
    </div>
  </section>

  <section v-if="searchResult && !searchResult.matched" class="mx-auto mt-6 max-w-4xl px-4">
    <div class="rounded-[2rem] border border-border/70 bg-card/70 p-5 shadow-lg backdrop-blur-xl sm:p-7">
      <div>
        <span class="badge">下一步</span>
        <h2 class="mt-3 text-2xl font-semibold">贡献已在本地验证的解压密码</h2>
        <p class="mt-2 text-sm leading-6 text-muted-foreground">密码将通过服务端认证加密保存；数据库仅使用密钥化标签去重，不建立明文索引。</p>
      </div>
      <div class="mt-5 grid gap-4">
        <div class="rounded-2xl border border-border/60 bg-muted/35 p-4 text-sm leading-6 text-muted-foreground">
          <strong class="text-foreground">网页提交统一进入待验证池。</strong> 游客和登录用户提交后，需至少 4 名不同登录用户确认正确才会进入总哈希池；登录用户通过桌面端完成有效签名验证成功时可直接进入总哈希池。
          <span v-if="!auth.isAuthenticated" class="mt-2 block">游客提交不记录个人贡献历史或积分；<RouterLink class="font-medium text-primary hover:underline" to="/login">登录后提交</RouterLink>可保留贡献记录。</span>
        </div>
        <div class="grid gap-2">
          <label for="candidate-password" class="text-sm font-medium">解压密码</label>
          <Input id="candidate-password" v-model="candidatePassword" type="password" autocomplete="off" maxlength="512" />
        </div>
        <label class="flex items-start gap-3 text-sm text-muted-foreground">
          <Checkbox v-model="authorizationConfirmed" class="mt-0.5" />
          <span>我确认自己拥有该压缩包，或已获明确授权进行恢复和贡献。</span>
        </label>
        <Button class="w-full rounded-full sm:w-fit" type="button" :disabled="!canSubmit || submitting" @click="submitContribution">{{ submitting ? "提交中…" : auth.isAuthenticated ? "提交网页待验证贡献" : "以游客身份提交待验证贡献" }}</Button>
      </div>
    </div>
  </section>

  <section class="mx-auto grid max-w-6xl gap-5 px-4 py-10 lg:grid-cols-3" aria-label="站点发现与排行榜">
    <div class="rounded-3xl border border-border/60 bg-card/70 p-5 shadow-lg backdrop-blur-xl">
      <div class="flex items-start justify-between gap-3">
        <div><p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">DISCOVERY</p><h2 class="mt-2 text-xl font-semibold">热门哈希值</h2></div>
        <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">TOP 5</span>
      </div>
      <div v-if="discoveryLoading" class="mt-5 space-y-3"><div v-for="index in 5" :key="index" class="h-14 animate-pulse rounded-2xl bg-muted" /></div>
      <div v-else-if="discovery.hot_hashes.length" class="mt-5 space-y-2">
        <RouterLink v-for="(item, index) in discovery.hot_hashes" :key="`${item.algorithm}-${item.digest}`" :to="`/hash/${item.algorithm}/${item.digest}`" class="flex items-center gap-3 rounded-2xl border border-border/60 bg-background/55 p-3 transition hover:border-primary/30 hover:bg-primary/5">
          <span class="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">{{ index + 1 }}</span>
          <span class="min-w-0 flex-1"><strong class="block truncate font-mono text-sm">{{ item.digest }}</strong><small class="text-muted-foreground">{{ item.algorithm.toUpperCase() }} · 热度 {{ item.heat_score }}</small></span>
          <span class="text-xs text-muted-foreground">赞 {{ item.like_count }}</span>
        </RouterLink>
      </div>
      <p v-else class="mt-5 rounded-2xl border border-dashed p-5 text-sm text-muted-foreground">暂无可排行的哈希互动数据。</p>
    </div>

    <div class="rounded-3xl border border-border/60 bg-card/70 p-5 shadow-lg backdrop-blur-xl">
      <div class="flex items-start justify-between gap-3"><div><p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">CONTRIBUTORS</p><h2 class="mt-2 text-xl font-semibold">用户贡献排行榜</h2></div><span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">TOP 5</span></div>
      <div v-if="discoveryLoading" class="mt-5 space-y-3"><div v-for="index in 5" :key="index" class="h-14 animate-pulse rounded-2xl bg-muted" /></div>
      <ol v-else-if="discovery.contribution_leaders.length" class="mt-5 space-y-2">
        <li v-for="item in discovery.contribution_leaders" :key="item.uid" class="flex items-center gap-3 rounded-2xl border border-border/60 bg-background/55 p-3">
          <span class="flex size-8 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-accent-foreground">{{ item.rank }}</span>
          <RouterLink class="min-w-0 flex-1 truncate font-medium hover:text-primary" :to="`/community/users/${item.username}`">{{ item.username }}</RouterLink>
          <span class="text-sm font-semibold">{{ item.score }} 次</span>
        </li>
      </ol>
      <p v-else class="mt-5 rounded-2xl border border-dashed p-5 text-sm text-muted-foreground">暂无有效贡献排行数据。</p>
    </div>

    <div class="rounded-3xl border border-border/60 bg-card/70 p-5 shadow-lg backdrop-blur-xl">
      <div class="flex items-start justify-between gap-3"><div><p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">POINTS</p><h2 class="mt-2 text-xl font-semibold">用户积分排行榜</h2></div><span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">TOP 5</span></div>
      <div v-if="discoveryLoading" class="mt-5 space-y-3"><div v-for="index in 5" :key="index" class="h-14 animate-pulse rounded-2xl bg-muted" /></div>
      <ol v-else-if="discovery.points_leaders.length" class="mt-5 space-y-2">
        <li v-for="item in discovery.points_leaders" :key="item.uid" class="flex items-center gap-3 rounded-2xl border border-border/60 bg-background/55 p-3">
          <span class="flex size-8 items-center justify-center rounded-full bg-emerald-500/10 text-sm font-semibold text-emerald-700 dark:text-emerald-300">{{ item.rank }}</span>
          <RouterLink class="min-w-0 flex-1 truncate font-medium hover:text-primary" :to="`/community/users/${item.username}`">{{ item.username }}</RouterLink>
          <span class="text-sm font-semibold">{{ item.score }} 分</span>
        </li>
      </ol>
      <p v-else class="mt-5 rounded-2xl border border-dashed p-5 text-sm text-muted-foreground">暂无已结算积分排行数据。</p>
    </div>
  </section>

  <section class="mx-auto grid max-w-4xl gap-4 px-4 py-10 sm:grid-cols-3">
    <div class="rounded-3xl border border-border/60 bg-card/55 p-5 backdrop-blur-xl"><span class="text-2xl">◌</span><h2 class="mt-4 font-semibold">本地计算</h2><p class="mt-2 text-sm leading-6 text-muted-foreground">文件内容留在浏览器，只提交用于检索的完整指纹。</p></div>
    <div class="rounded-3xl border border-border/60 bg-card/55 p-5 backdrop-blur-xl"><span class="text-2xl">✦</span><h2 class="mt-4 font-semibold">可信候选</h2><p class="mt-2 text-sm leading-6 text-muted-foreground">社区验证、反馈与信誉事件共同决定候选可信度。</p></div>
    <div class="rounded-3xl border border-border/60 bg-card/55 p-5 backdrop-blur-xl"><span class="text-2xl">↗</span><h2 class="mt-4 font-semibold">授权协作</h2><p class="mt-2 text-sm leading-6 text-muted-foreground">仅处理本人拥有或已获明确授权的压缩包。</p></div>
  </section>
</template>
