<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const secret = ref("");
const provisioningUri = ref("");
const code = ref("");
const error = ref("");
const busy = ref(false);

onMounted(async () => {
  try {
    const setup = await auth.beginTotpSetup();
    secret.value = setup.secret;
    provisioningUri.value = setup.provisioning_uri;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "无法生成 TOTP 配置";
  }
});

async function confirm() {
  busy.value = true;
  error.value = "";
  try {
    await auth.confirmTotpSetup(code.value);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "验证码确认失败";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="panel stack">
    <div><div class="eyebrow">管理员安全基线</div><h1>绑定 TOTP</h1></div>
    <p class="muted">请将下方合成配置录入认证器。密钥只在本次设置流程中显示。</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="secret" class="stack">
      <div class="field"><label>手工密钥</label><input :value="secret" readonly /></div>
      <details><summary>配置 URI</summary><code style="overflow-wrap:anywhere">{{ provisioningUri }}</code></details>
      <form class="form stack" @submit.prevent="confirm">
        <div class="field"><label for="confirm-code">动态验证码</label><input id="confirm-code" v-model="code" inputmode="numeric" autocomplete="one-time-code" minlength="6" maxlength="8" required /></div>
        <button class="button" :disabled="busy">{{ busy ? "确认中…" : "确认并启用" }}</button>
      </form>
    </div>
  </section>
</template>
