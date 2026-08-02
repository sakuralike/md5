<script setup lang="ts">
import type { MySubmissionsResponse } from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { apiRequest } from "../services/api";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const data = ref<MySubmissionsResponse | null>(null);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    data.value = await apiRequest<MySubmissionsResponse>(
      "/me/submissions?page=1&page_size=50",
      {},
      auth.accessToken,
    );
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "贡献记录加载失败";
  } finally {
    loading.value = false;
  }
});

function shortDigest(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function statusLabel(status: string): string {
  return {
    pending: "待验证",
    verified: "已验证",
    rejected: "已拒绝",
    quarantined: "已隔离",
  }[status] ?? status;
}
</script>

<template>
  <section class="panel stack">
    <div>
      <div class="eyebrow">用户中心</div>
      <h1 class="page-title">我的贡献</h1>
      <p class="lead">查看授权贡献证据及当前候选状态。此页面不会返回或缓存候选密码。</p>
    </div>
    <p v-if="loading" class="muted">正在加载贡献记录…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <div v-else-if="data && data.items.length === 0" class="empty-state">
      <strong>还没有贡献记录</strong>
      <RouterLink class="button" to="/">前往本地查询</RouterLink>
    </div>
    <div v-else-if="data" class="submission-list">
      <article v-for="item in data.items" :key="item.id" class="candidate-card submission-card">
        <div class="stack compact-stack">
          <div class="actions">
            <span class="badge">{{ statusLabel(item.candidate_status) }}</span>
            <span class="muted">{{ new Date(item.created_at).toLocaleString() }}</span>
          </div>
          <code v-for="fingerprint in item.fingerprints" :key="fingerprint.algorithm">
            {{ fingerprint.algorithm.toUpperCase() }} · {{ shortDigest(fingerprint.digest) }}
          </code>
          <small>候选 ID {{ item.candidate_id }}</small>
          <small>授权声明版本 {{ item.authorization_version }} · 来源 {{ item.source }}</small>
          <RouterLink
            v-if="item.candidate_status === 'rejected' || item.candidate_status === 'quarantined'"
            class="button secondary"
            :to="{ path: '/trust-cases', query: { kind: 'appeal', candidate_id: item.candidate_id } }"
          >
            对此审核结果发起申诉
          </RouterLink>
        </div>
      </article>
    </div>
  </section>
</template>
