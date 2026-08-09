<script setup lang="ts">
import { Button } from "@/components/ui/button";
import { useAdminAuthStore } from "./stores/auth";

const auth = useAdminAuthStore();

const navigationItems = [
  { to: "/", label: "仪表盘" },
  { to: "/candidates", label: "候选审核" },
  { to: "/trust-cases", label: "举报申诉" },
  { to: "/risk-alerts", label: "风险告警" },
  { to: "/desktop-releases", label: "桌面发布" },
  { to: "/audit", label: "审计日志" },
  { to: "/users", label: "用户治理" },
  { to: "/role-changes", label: "角色审批" },
  { to: "/settings", label: "系统配置" },
] as const;
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-50 via-background to-sky-50/60 text-foreground">
    <header class="sticky top-0 z-40 border-b bg-background/95 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/85">
      <div class="mx-auto flex w-full max-w-screen-2xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6 lg:flex-nowrap lg:px-8">
        <RouterLink class="flex min-w-0 items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" to="/">
          <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-lg text-primary-foreground shadow-sm" aria-hidden="true">🛡️</span>
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
              class="shrink-0 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              active-class="bg-accent text-accent-foreground"
            >
              {{ item.label }}
            </RouterLink>
          </nav>
          <Button class="shrink-0" variant="outline" size="sm" @click="auth.logout()">退出</Button>
        </div>
      </div>
    </header>

    <main class="mx-auto min-h-[calc(100vh-4.5rem)] w-full max-w-screen-2xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <RouterView />
    </main>
  </div>
</template>
