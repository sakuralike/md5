<script setup lang="ts">
import { ShieldCheck } from "lucide-vue-next";
import { ThemeToggle } from "@password-detective/web-ui/theme-toggle";
import AdminSettingsNavigation from "@/components/AdminSettingsNavigation.vue";
import { Button } from "@/components/ui/button";
import { dashboardNavigationItem } from "@/lib/adminNavigation";
import { useAdminAuthStore } from "./stores/auth";

const auth = useAdminAuthStore();
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <a
      href="#main-content"
      class="sr-only z-50 rounded-md bg-background px-4 py-2 text-foreground shadow-lg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
    >
      跳到主要内容
    </a>
    <header class="sticky top-0 z-50 border-b border-border/70 bg-background/80 px-4 py-3 backdrop-blur-xl sm:px-6">
      <div class="mx-auto flex w-full max-w-screen-2xl flex-wrap items-center gap-3 lg:flex-nowrap">
        <RouterLink class="flex min-w-0 items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" to="/">
          <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-accent text-primary-foreground shadow-md" aria-hidden="true">
            <ShieldCheck class="size-5" />
          </span>
          <span class="min-w-0">
            <strong class="block truncate text-sm font-semibold tracking-tight sm:text-base">密码侦探社 · 管理端</strong>
            <small class="block truncate text-xs text-muted-foreground">受控治理与安全运营</small>
          </span>
        </RouterLink>

        <div class="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2 lg:flex-nowrap">
          <ThemeToggle />
          <template v-if="auth.isAuthenticated">
            <nav class="flex items-center gap-1" aria-label="管理主导航">
            <RouterLink
              :to="dashboardNavigationItem.path"
              class="rounded-full px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-card hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              exact-active-class="bg-card text-primary shadow-sm"
            >
              {{ dashboardNavigationItem.label }}
            </RouterLink>
            </nav>
            <AdminSettingsNavigation mode="mobile" />
            <Button class="shrink-0 rounded-full" variant="outline" size="sm" @click="auth.logout()">退出</Button>
          </template>
        </div>
      </div>
    </header>

    <AdminSettingsNavigation v-if="auth.isAuthenticated" mode="desktop" />

    <main
      id="main-content"
      class="mx-auto min-h-screen w-full max-w-screen-2xl px-4 pb-7 pt-8 sm:px-6 sm:pb-8 lg:pb-10 [&_input]:max-h-10 [&_input]:h-10 [&_textarea]:max-h-32 [&_[role=combobox]]:max-h-10"
      :class="auth.isAuthenticated ? 'lg:pl-[18rem] lg:pr-8' : 'lg:px-8'"
      tabindex="-1"
    >
      <RouterView />
    </main>
  </div>
</template>
