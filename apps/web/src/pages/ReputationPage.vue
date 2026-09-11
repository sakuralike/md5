<script setup lang="ts">
import type {
  FeedbackOutcome,
  PointsLedgerStatus,
  TrustProfileResponse,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { loadTrustCenter, type TrustCenterData } from "../services/reputation";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const data = ref<TrustCenterData | null>(null);
const loading = ref(true);
const error = ref("");

const reputationPercent = computed(() => {
  const profile = data.value?.profile;
  if (!profile) return 0;
  const range = profile.reputation_max - profile.reputation_min;
  return range > 0 ? ((profile.reputation_score - profile.reputation_min) / range) * 100 : 0;
});

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    data.value = await loadTrustCenter(auth.accessToken);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "积分与信誉记录加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function pointStatusLabel(status: PointsLedgerStatus): string {
  return { posted: "已入账", pending: "待结算", reversed: "已冲正" }[status];
}

function feedbackLabel(outcome: FeedbackOutcome): string {
  return outcome === "success" ? "成功" : "失败";
}

function eventLabel(eventType: string): string {
  return {
    "submission.pending": "候选贡献",
    "verification.accepted": "有效验证",
    "contribution.verified": "有效贡献",
    "reward.contribution.invalidate": "贡献奖励扣回",
    "reward.verification.invalidate": "验证奖励扣回",
    "reward.contribution.restore": "贡献奖励恢复",
    "reward.verification.restore": "验证奖励恢复",
    "activity.login_day": "每日活跃",
    "growth.reward.contribution.invalidate": "有效贡献成长值扣回",
    "growth.reward.verification.invalidate": "有效验证成长值扣回",
    "growth.reward.contribution.restore": "有效贡献成长值恢复",
    "growth.reward.verification.restore": "有效验证成长值恢复",
  }[eventType] ?? eventType;
}

function scoreText(profile: TrustProfileResponse): string {
  return `${profile.reputation_score} / ${profile.reputation_max}`;
}
</script>

<template>
  <section class="panel stack">
    <div class="actions">
      <div>
        <div class="eyebrow">用户中心</div>
        <h1 class="page-title">用户等级、积分与信誉</h1>
        <p class="lead">成长值决定长期等级权益；积分用于激励结算，信誉用于风控判断，三者独立记录。</p>
      </div>
      <Button type="button" variant="outline" :disabled="loading" @click="load">刷新</Button>
    </div>

    <p v-if="loading" class="muted" role="status" aria-live="polite">正在加载积分与信誉记录…</p>
    <p v-if="error" class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert" aria-live="assertive">{{ error }}</p>

    <template v-if="data">
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <article class="card stack compact-stack sm:col-span-2 xl:col-span-1">
          <div class="actions">
            <span class="eyebrow">用户等级</span>
            <span class="badge">{{ data.profile.level.current.name }}</span>
          </div>
          <strong class="text-2xl font-semibold sm:text-3xl">
            {{ data.profile.level.growth_points }} 成长值
          </strong>
          <Progress
            class="h-2.5 bg-muted"
            :model-value="data.profile.level.progress_percent"
            :max="100"
            aria-label="用户等级成长进度"
          />
          <small v-if="data.profile.level.next">
            距 {{ data.profile.level.next.name }} 还需 {{ data.profile.level.points_to_next_level }} 成长值
          </small>
          <small v-else>已达到当前最高等级</small>
          <small>
            每日揭示 {{ data.profile.level.current.entitlements.daily_reveal_quota }} 次 ·
            {{ data.profile.level.current.entitlements.can_submit ? "可提交档案" : "暂停提交档案" }}
          </small>
        </article>
        <article class="card stack compact-stack">
          <span class="eyebrow">信誉分</span>
          <strong class="text-2xl font-semibold sm:text-3xl">{{ scoreText(data.profile) }}</strong>
          <Progress
            class="h-2.5 bg-muted"
            :model-value="reputationPercent"
            :max="100"
            aria-label="信誉分完成度"
          />
          <small>初始 50 分，所有增减均记录不可变事件。</small>
        </article>
        <article class="card stack compact-stack">
          <span class="eyebrow">可用积分</span>
          <strong class="text-2xl font-semibold sm:text-3xl">{{ data.profile.points.available }}</strong>
          <small>
            待结算 {{ data.profile.points.pending }} · 已冲正 {{ data.profile.points.reversed }}
          </small>
        </article>
        <article class="card stack compact-stack">
          <span class="eyebrow">贡献</span>
          <strong class="text-2xl font-semibold sm:text-3xl">
            {{ data.profile.contributions.verified }} / {{ data.profile.contributions.total }}
          </strong>
          <small>当前已验证贡献 / 全部贡献</small>
        </article>
        <article class="card stack compact-stack">
          <span class="eyebrow">有效反馈</span>
          <strong class="text-2xl font-semibold sm:text-3xl">
            {{ data.profile.feedback.effective_success }} 成功 ·
            {{ data.profile.feedback.effective_failure }} 失败
          </strong>
          <small>共 {{ data.profile.feedback.history_events }} 条反馈修订事件</small>
        </article>
      </div>

      <div class="grid items-start gap-5 lg:grid-cols-3">
        <div class="card stack">
          <h2>积分流水</h2>
          <div v-if="data.points.items.length === 0" class="empty-state">暂无积分流水</div>
          <article
            v-for="item in data.points.items"
            :key="item.id"
            class="grid gap-2 border-t border-border/60 py-3.5"
          >
            <div class="actions">
              <strong>{{ eventLabel(item.event_type) }}</strong>
              <span class="badge">{{ pointStatusLabel(item.status) }}</span>
            </div>
            <span>{{ item.amount > 0 ? "+" : "" }}{{ item.amount }} 积分</span>
            <small class="muted">{{ formatDate(item.created_at) }}</small>
          </article>
        </div>

        <div class="card stack">
          <h2>信誉事件</h2>
          <div v-if="data.reputation.items.length === 0" class="empty-state">暂无信誉变更</div>
          <article
            v-for="item in data.reputation.items"
            :key="item.id"
            class="grid gap-2 border-t border-border/60 py-3.5"
          >
            <div class="actions">
              <strong>{{ eventLabel(item.event_type) }}</strong>
              <span class="badge">{{ item.amount > 0 ? "+" : "" }}{{ item.amount }}</span>
            </div>
            <span>{{ item.previous_score }} → {{ item.next_score }}</span>
            <small class="muted">{{ item.rule_version }} · {{ formatDate(item.created_at) }}</small>
          </article>
        </div>

        <div class="card stack">
          <h2>成长值流水</h2>
          <div v-if="data.growth.items.length === 0" class="empty-state">暂无成长值变更</div>
          <article
            v-for="item in data.growth.items"
            :key="item.id"
            class="grid gap-2 border-t border-border/60 py-3.5"
          >
            <div class="actions">
              <strong>{{ eventLabel(item.event_type) }}</strong>
              <span class="badge">{{ item.amount > 0 ? "+" : "" }}{{ item.amount }}</span>
            </div>
            <small class="muted">{{ item.rule_version }} · {{ formatDate(item.created_at) }}</small>
          </article>
        </div>
      </div>

      <div class="card stack">
        <h2>反馈历史</h2>
        <div v-if="data.feedback.items.length === 0" class="empty-state">暂无反馈历史</div>
        <article
          v-for="item in data.feedback.items"
          :key="item.evidence_event_id"
          class="grid gap-2 border-t border-border/60 py-3.5"
        >
          <div class="actions">
            <strong>{{ feedbackLabel(item.outcome) }}反馈</strong>
            <span class="badge">修订 {{ item.revision }}</span>
          </div>
          <code>{{ item.candidate_id }}</code>
          <small class="muted">
            {{ item.rule_version }} · 候选状态 {{ item.candidate_status }} ·
            {{ formatDate(item.created_at) }}
          </small>
        </article>
      </div>
    </template>
  </section>
</template>
