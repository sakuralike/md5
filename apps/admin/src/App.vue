<script setup lang="ts">
import { Button } from "@/components/ui/button";
import { useAdminAuthStore } from "./stores/auth";

const auth = useAdminAuthStore();

const navigationItems = [
  { to: "/", label: "仪表盘" },
  { to: "/candidates", label: "候选审核" },
  { to: "/trust-cases", label: "举报申诉" },
  { to: "/community", label: "社区治理" },
  { to: "/community/settings", label: "社区配置" },
  { to: "/risk-alerts", label: "风险告警" },
  { to: "/desktop-releases", label: "桌面发布" },
  { to: "/audit", label: "审计日志" },
  { to: "/users", label: "用户治理" },
  { to: "/role-changes", label: "角色审批" },
  { to: "/settings", label: "系统配置" },
] as const;
</script>

<template>
  <div class="relative isolate min-h-screen overflow-x-hidden bg-gradient-to-br from-background via-secondary/40 to-muted text-foreground">
    <div class="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <span class="absolute -right-24 -top-24 h-80 w-80 rounded-full bg-primary/20 blur-3xl"></span>
      <span class="absolute -bottom-32 -left-24 h-96 w-96 rounded-full bg-accent/15 blur-3xl"></span>
      <span class="absolute left-1/3 top-1/3 h-72 w-72 rounded-full bg-secondary/80 blur-3xl"></span>
    </div>
    <a
      href="#main-content"
      class="sr-only z-50 rounded-md bg-background px-4 py-2 text-foreground shadow-lg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
    >
      跳到主要内容
    </a>
    <header class="sticky top-0 z-40 px-3 pt-3 sm:px-5">
      <div class="mx-auto flex w-full max-w-screen-2xl flex-wrap items-center gap-3 rounded-2xl border border-card/80 bg-card/70 px-4 py-3 shadow-lg backdrop-blur-2xl sm:px-5 lg:flex-nowrap">
        <RouterLink class="flex min-w-0 items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" to="/">
          <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-accent text-lg text-primary-foreground shadow-md" aria-hidden="true">🛡️</span>
          <span class="min-w-0">
            <strong class="block truncate text-sm font-semibold tracking-tight sm:text-base">密码侦探社 · 管理端</strong>
            <small class="block truncate text-xs text-muted-foreground">受控治理与安全运营</small>
          </span>
        </RouterLink>

        <div v-if="auth.isAuthenticated" class="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2 lg:flex-nowrap">
          <nav class="order-2 flex w-full gap-1 overflow-x-auto pb-1 lg:order-none lg:ml-4 lg:w-auto lg:flex-1 lg:justify-end lg:pb-0" aria-label="管理导航">
            <RouterLink
              v-for="item in navigationItems"
              :key="item.to"
              :to="item.to"
              class="shrink-0 rounded-full px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-card hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              active-class="bg-card text-primary shadow-sm"
            >
              {{ item.label }}
            </RouterLink>
          </nav>
          <Button class="shrink-0 rounded-full border-card/80 bg-card/70" variant="outline" size="sm" @click="auth.logout()">退出</Button>
        </div>
      </div>
    </header>

    <main id="main-content" class="mx-auto min-h-[calc(100vh-5.5rem)] w-full max-w-screen-2xl px-4 py-7 sm:px-6 lg:px-8 lg:py-10" tabindex="-1">
      <RouterView />
    </main>
  </div>
</template>
