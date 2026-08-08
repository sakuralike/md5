<script setup lang="ts">
import type {
  AppealReason,
  ReportReason,
  TrustCaseKind,
  TrustCaseListResponse,
  TrustCaseSummary,
} from "@password-detective/api-contract";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
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
import { Textarea } from "@/components/ui/textarea";
import {
  createAppeal,
  createReport,
  createTrustCaseSubmissionKey,
  listMyTrustCases,
} from "../services/trustCases";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const caseKind = ref<TrustCaseKind>(route.query.kind === "appeal" ? "appeal" : "report");
const candidateId = ref(typeof route.query.candidate_id === "string" ? route.query.candidate_id : "");
const relatedCaseId = ref("");
const reasonCode = ref<string>(
  caseKind.value === "appeal" ? "appeal.decision_incorrect" : "report.invalid_candidate",
);
const description = ref("");
const data = ref<TrustCaseListResponse | null>(null);
const loading = ref(true);
const submitting = ref(false);
const error = ref("");
const success = ref("");

const reportReasons: Array<{ value: ReportReason; label: string }> = [
  { value: "report.invalid_candidate", label: "候选内容不准确" },
  { value: "report.policy_violation", label: "疑似违反社区规则" },
  { value: "report.misleading_metadata", label: "元数据误导" },
  { value: "report.other", label: "其他" },
];
const appealReasons: Array<{ value: AppealReason; label: string }> = [
  { value: "appeal.decision_incorrect", label: "审核决定不正确" },
  { value: "appeal.new_evidence", label: "有新的证据" },
  { value: "appeal.context_missing", label: "审核遗漏了重要背景" },
  { value: "appeal.other", label: "其他" },
];
const statusClassMap: Record<TrustCaseSummary["status"], string> = {
  open: "text-destructive",
  in_review: "text-primary",
  resolved: "text-accent-foreground",
  dismissed: "text-muted-foreground",
};

const reasonOptions = computed(() =>
  caseKind.value === "appeal" ? appealReasons : reportReasons,
);
const isAppeal = computed(() => caseKind.value === "appeal");
const canSubmit = computed(
  () =>
    candidateId.value.trim().length > 0 &&
    reasonCode.value.length > 0 &&
    (!isAppeal.value || description.value.trim().length > 0),
);

watch(caseKind, (kind) => {
  reasonCode.value = kind === "appeal" ? appealReasons[0].value : reportReasons[0].value;
  if (kind === "report") relatedCaseId.value = "";
});

onMounted(() => loadCases());

async function loadCases(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    data.value = await listMyTrustCases(auth.accessToken);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "案件加载失败";
  } finally {
    loading.value = false;
  }
}

async function submitCase(): Promise<void> {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    if (isAppeal.value) {
      await createAppeal(
        {
          candidate_id: candidateId.value.trim(),
          related_case_id: relatedCaseId.value.trim() || null,
          reason_code: reasonCode.value as AppealReason,
          description: description.value.trim(),
        },
        auth.accessToken,
        createTrustCaseSubmissionKey("appeal"),
      );
      success.value = "申诉已提交，工作人员会在案件队列中处理。";
    } else {
      await createReport(
        {
          candidate_id: candidateId.value.trim(),
          reason_code: reasonCode.value as ReportReason,
          description: description.value.trim() || null,
        },
        auth.accessToken,
        createTrustCaseSubmissionKey("report"),
      );
      success.value = "举报已提交，感谢你帮助维护内容质量。";
    }
    candidateId.value = "";
    relatedCaseId.value = "";
    description.value = "";
    await loadCases();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "案件提交失败";
  } finally {
    submitting.value = false;
  }
}

function reasonLabel(value: string): string {
  return [...reportReasons, ...appealReasons].find((item) => item.value === value)?.label ?? value;
}

function kindLabel(kind: TrustCaseKind): string {
  return { report: "举报", appeal: "贡献申诉", account_appeal: "账号申诉" }[kind];
}

function subjectLabel(item: TrustCaseSummary): string {
  if (item.subject_type === "account") return `账号 ${item.target_user_id ?? "—"}`;
  if (item.subject_type === "risk_alert") return `风险告警 ${item.risk_alert_id ?? "—"}`;
  return `候选 ${item.candidate_id ?? "—"}`;
}

function statusLabel(status: TrustCaseSummary["status"]): string {
  return {
    open: "待处理",
    in_review: "处理中",
    resolved: "已解决",
    dismissed: "已驳回",
  }[status];
}

function statusClass(status: TrustCaseSummary["status"]): string {
  return `text-sm font-bold ${statusClassMap[status]}`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}
</script>

<template>
  <section class="panel stack">
    <div>
      <div class="eyebrow">用户中心</div>
      <h1 class="page-title">举报与申诉</h1>
      <p class="lead">
        只提交候选内容的客观问题或你本人贡献的审核申诉。请勿在说明中填写密码、令牌、密钥或其他敏感信息。
      </p>
    </div>

    <div class="grid items-start gap-6 lg:grid-cols-[minmax(280px,0.9fr)_minmax(0,1.1fr)]">
      <form class="card stack max-w-none" @submit.prevent="submitCase">
        <div class="actions">
          <Button
            type="button"
            :variant="caseKind === 'report' ? 'default' : 'outline'"
            :aria-pressed="caseKind === 'report'"
            @click="caseKind = 'report'"
          >
            提交举报
          </Button>
          <Button
            type="button"
            :variant="caseKind === 'appeal' ? 'default' : 'outline'"
            :aria-pressed="caseKind === 'appeal'"
            @click="caseKind = 'appeal'"
          >
            发起申诉
          </Button>
        </div>

        <p v-if="isAppeal" class="muted">
          申诉仅适用于你本人提交且当前状态为“已拒绝”或“已隔离”的贡献。
        </p>
        <p v-else class="muted">举报面向候选内容本身，系统会将其交给内容治理队列复核。</p>

        <div class="field">
          <Label for="trust-candidate-id">候选 ID</Label>
          <Input
            id="trust-candidate-id"
            v-model="candidateId"
            autocomplete="off"
            placeholder="粘贴候选 ID"
            required
          />
        </div>

        <div v-if="isAppeal" class="field">
          <Label for="trust-related-case-id">关联举报 ID（可选）</Label>
          <Input
            id="trust-related-case-id"
            v-model="relatedCaseId"
            autocomplete="off"
            placeholder="如果已有相关举报，可填写案件 ID"
          />
        </div>

        <div class="field">
          <Label for="trust-reason">原因</Label>
          <Select v-model="reasonCode">
            <SelectTrigger id="trust-reason">
              <SelectValue placeholder="选择原因" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="option in reasonOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="field">
          <Label for="trust-description">
            说明 <span class="muted">{{ isAppeal ? "（必填）" : "（可选）" }}</span>
          </Label>
          <Textarea
            id="trust-description"
            v-model="description"
            rows="5"
            maxlength="1000"
            :required="isAppeal"
            placeholder="请描述可核验的事实、时间或上下文，不要粘贴任何秘密材料"
          />
        </div>

        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="success" class="success">{{ success }}</p>
        <Button type="submit" :disabled="submitting || !canSubmit">
          {{ submitting ? "提交中…" : isAppeal ? "提交申诉" : "提交举报" }}
        </Button>
      </form>

      <div class="card stack">
        <div class="actions">
          <div>
            <div class="eyebrow">透明处理</div>
            <h2>我的案件</h2>
          </div>
          <Button type="button" variant="outline" :disabled="loading" @click="loadCases">
            刷新
          </Button>
        </div>
        <p v-if="loading" class="muted">正在加载案件…</p>
        <p v-else-if="error && !data" class="error">{{ error }}</p>
        <div v-else-if="data && data.items.length === 0" class="empty-state">
          <strong>暂无举报或申诉</strong>
          <span>提交后可以在这里查看处理状态。</span>
        </div>
        <div v-else class="grid gap-3">
          <article
            v-for="item in data?.items"
            :key="item.id"
            class="candidate-card items-stretch"
          >
            <div class="actions justify-start">
              <span class="badge">{{ kindLabel(item.kind) }}</span>
              <span :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span>
              <span class="muted">{{ formatDate(item.created_at) }}</span>
            </div>
            <strong>{{ reasonLabel(item.reason_code) }}</strong>
            <code class="break-all text-xs text-muted-foreground">{{ item.id }}</code>
            <small>{{ subjectLabel(item) }}</small>
            <p v-if="item.resolution_note" class="muted">处理说明：{{ item.resolution_note }}</p>
          </article>
        </div>
      </div>
    </div>

    <div class="empty-state">
      <strong>需要从贡献记录发起申诉？</strong>
      <span>前往“我的贡献”，在已拒绝或已隔离的本人贡献旁点击申诉。</span>
      <RouterLink class="button secondary" to="/submissions">查看我的贡献</RouterLink>
    </div>
  </section>
</template>
