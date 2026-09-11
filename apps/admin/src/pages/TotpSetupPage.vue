<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
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

async function confirm(): Promise<void> {
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
    <div>
      <div class="eyebrow">可选安全增强</div>
      <h1>绑定 TOTP</h1>
    </div>
    <p class="muted">TOTP 默认关闭。需要增强账号安全时，可将下方配置录入认证器；密钥只在本次设置流程中显示。</p>
    <p v-if="error" class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>
    <div v-if="secret" class="stack">
      <div class="field">
        <Label for="totp-secret">手工密钥</Label>
        <Input id="totp-secret" :model-value="secret" readonly />
      </div>
      <details>
        <summary>配置 URI</summary>
        <code class="break-all">{{ provisioningUri }}</code>
      </details>
      <form class="form stack" @submit.prevent="confirm">
        <div class="field">
          <Label for="confirm-code">动态验证码</Label>
          <Input
            id="confirm-code"
            v-model="code"
            inputmode="numeric"
            autocomplete="one-time-code"
            minlength="6"
            maxlength="8"
            required
          />
        </div>
        <Button type="submit" :disabled="busy">
          {{ busy ? "确认中…" : "确认并启用" }}
        </Button>
      </form>
    </div>
  </section>
</template>
