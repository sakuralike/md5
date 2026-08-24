<script setup lang="ts">
import { Copy, Gift, RefreshCw, UsersRound } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getMyReferralProfile } from "../services/referrals";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const data = ref<Awaited<ReturnType<typeof getMyReferralProfile>> | null>(null);
const loading = ref(true);
const error = ref("");
const message = ref("");
const referralUrl = computed(() => {
  if (!data.value || typeof window === "undefined") return data.value?.referral_url ?? "";
  return new URL(data.value.referral_url, window.location.origin).toString();
});

async function load(): Promise<void> {
  if (!auth.accessToken) return;
  loading.value = true;
  error.value = "";
  try {
    data.value = await getMyReferralProfile(auth.accessToken);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "邀请链接暂时无法加载";
  } finally {
    loading.value = false;
  }
}

async function copyReferralLink(): Promise<void> {
  if (!data.value) return;
  try {
    await navigator.clipboard.writeText(referralUrl.value);
    message.value = "邀请链接已复制。";
  } catch {
    error.value = "复制失败，请手动复制邀请链接。";
  }
}

onMounted(() => void load());
</script>

<template>
  <section class="mx-auto w-full max-w-4xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
    <header class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <div class="flex items-center gap-2 text-sm font-medium text-primary"><Gift class="size-4" />邀请奖励</div>
        <h1 class="text-3xl font-semibold tracking-tight">邀请好友注册</h1>
        <p class="text-sm leading-6 text-muted-foreground">分享你的专属链接。好友完成注册后，你和好友各获得相同的积分奖励。</p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load"><RefreshCw class="mr-2 size-4" />刷新</Button>
    </header>

    <p v-if="error" class="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>
    <p v-if="message" class="rounded-md bg-primary/10 px-4 py-3 text-sm text-primary" role="status">{{ message }}</p>

    <Card v-if="data" class="border-border/70">
      <CardHeader><CardTitle>我的专属邀请链接</CardTitle><CardDescription>链接长期有效；每位新用户只能绑定一次邀请关系。</CardDescription></CardHeader>
      <CardContent class="space-y-5">
        <div class="space-y-2"><Label for="referral-link">邀请链接</Label><div class="flex gap-2"><Input id="referral-link" :model-value="referralUrl" readonly /><Button size="icon" type="button" title="复制邀请链接" aria-label="复制邀请链接" @click="copyReferralLink"><Copy class="size-4" /></Button></div></div>
        <div class="grid gap-4 sm:grid-cols-3">
          <div class="rounded-md border p-4"><div class="flex items-center gap-2 text-sm text-muted-foreground"><Gift class="size-4" />双方奖励</div><strong class="mt-2 block text-2xl">{{ data.reward_points }} 积分</strong></div>
          <div class="rounded-md border p-4"><div class="flex items-center gap-2 text-sm text-muted-foreground"><UsersRound class="size-4" />成功邀请</div><strong class="mt-2 block text-2xl">{{ data.referral_count }} 人</strong></div>
          <div class="rounded-md border p-4"><div class="flex items-center gap-2 text-sm text-muted-foreground"><Badge variant="secondary">积分</Badge>累计获得</div><strong class="mt-2 block text-2xl">{{ data.total_points_earned }}</strong></div>
        </div>
      </CardContent>
    </Card>
    <Card v-else-if="loading"><CardContent class="p-8 text-sm text-muted-foreground">正在加载邀请信息…</CardContent></Card>
  </section>
</template>
