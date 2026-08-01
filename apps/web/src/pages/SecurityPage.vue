<script setup lang="ts">
import type { Session } from "@password-detective/api-contract";
import { onMounted, ref } from "vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const sessions = ref<Session[]>([]);
const error = ref("");
const busyId = ref("");

async function load() {
  try { sessions.value = await auth.listSessions(); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : "无法加载会话"; }
}

async function revoke(id: string) {
  busyId.value = id;
  try { await auth.revokeSession(id); await load(); }
  catch (caught) { error.value = caught instanceof Error ? caught.message : "撤销失败"; }
  finally { busyId.value = ""; }
}

onMounted(load);
</script>

<template>
  <section class="panel stack">
    <div><div class="eyebrow">账号安全</div><h1>{{ auth.user?.username }}</h1><p class="muted">查看并撤销登录会话。IP 仅显示脱敏网段。</p></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div style="overflow-x:auto">
      <table class="table">
        <thead><tr><th>设备</th><th>IP 网段</th><th>最后活动</th><th>到期时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="session in sessions" :key="session.id">
            <td>{{ session.user_agent || "未知设备" }} <span v-if="session.current" class="badge">当前</span></td>
            <td>{{ session.ip_prefix || "未知" }}</td>
            <td>{{ new Date(session.last_used_at).toLocaleString() }}</td>
            <td>{{ new Date(session.expires_at).toLocaleString() }}</td>
            <td><button class="button danger" :disabled="busyId === session.id" @click="revoke(session.id)">撤销</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
