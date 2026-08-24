<script setup lang="ts">
import { KeyRound, Settings2 } from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import RegistrationManagement from "@/components/RegistrationManagement.vue";
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">系统管理 · 注册</p>
        <h1 class="flex items-center gap-2 text-2xl font-semibold tracking-tight"><KeyRound class="size-6 text-primary" />邀请码与邀请链接</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">管理管理员邀请码注册策略。开放注册时启用用户邀请链接；邀请码注册为第一优先级，两者不会同时生效。</p>
      </div>
      <Button variant="outline" as-child><RouterLink to="/settings#operational-policy"><Settings2 class="mr-2 size-4" />设置邀请奖励积分</RouterLink></Button>
    </header>
    <RegistrationManagement />
  </section>
</template>
