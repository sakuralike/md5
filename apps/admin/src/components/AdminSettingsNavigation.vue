<script setup lang="ts">
import {
  BadgeCheck,
  Globe2,
  History,
  MailCheck,
  Menu,
  Settings2,
  ShieldCheck,
  type LucideIcon,
} from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  adminNavigationGroups,
  adminSettingsNavigationItems,
  type AdminNavigationItem,
} from "@/lib/adminNavigation";

interface SystemSettingsSectionItem {
  label: string;
  to: string;
  icon: LucideIcon;
}

const props = withDefaults(defineProps<{ mode?: "desktop" | "mobile" }>(), {
  mode: "desktop",
});

const systemSettingsSections: readonly SystemSettingsSectionItem[] = [
  { label: "站点外观", to: "/settings#site-appearance", icon: Globe2 },
  { label: "邮件投递", to: "/settings#email-delivery", icon: MailCheck },
  { label: "版本历史", to: "/settings#version-history", icon: History },
  { label: "运行策略", to: "/settings#operational-policy", icon: Settings2 },
  { label: "发布门禁", to: "/settings#publish-gate", icon: ShieldCheck },
];

function itemsForGroup(
  group: (typeof adminNavigationGroups)[number],
): readonly AdminNavigationItem[] {
  return adminSettingsNavigationItems.filter((item) => item.group === group);
}

function sectionsForPath(path: string): readonly SystemSettingsSectionItem[] {
  if (path === "/users") {
    return [{ label: "用户等级与权益", to: "/users#user-levels", icon: BadgeCheck }];
  }
  if (path === "/settings") return systemSettingsSections;
  return [];
}
</script>

<template>
  <aside
    v-if="props.mode === 'desktop'"
    class="fixed bottom-4 left-4 top-24 z-30 hidden w-64 overscroll-contain overflow-y-auto rounded-3xl border border-border/80 bg-card/95 p-4 shadow-xl backdrop-blur-2xl lg:block 2xl:left-[calc((100vw-1536px)/2+1rem)]"
    aria-label="后台设置导航"
  >
    <div class="border-b border-border/70 px-2 pb-4">
      <div class="flex items-center gap-2 text-primary">
        <Settings2 class="size-4" aria-hidden="true" />
        <span class="text-xs font-semibold uppercase tracking-[0.18em]">Admin settings</span>
      </div>
      <h2 class="mt-2 text-lg font-semibold text-foreground">后台设置导航</h2>
      <p class="mt-1 text-xs leading-5 text-muted-foreground">仪表盘以外的管理功能统一从固定导航进入。</p>
    </div>

    <div class="mt-4 space-y-5">
      <section v-for="group in adminNavigationGroups" :key="group">
        <h3 class="px-2 text-xs font-semibold text-muted-foreground">{{ group }}</h3>
        <nav class="mt-2 space-y-1" :aria-label="`${group}导航`">
          <div v-for="item in itemsForGroup(group)" :key="item.path">
            <RouterLink
              :to="item.path"
              class="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              exact-active-class="bg-primary text-primary-foreground shadow-sm hover:bg-primary hover:text-primary-foreground"
            >
              <component :is="item.icon" class="size-4 shrink-0" aria-hidden="true" />
              <span>{{ item.label }}</span>
            </RouterLink>

            <nav
              v-if="sectionsForPath(item.path).length > 0"
              class="ml-5 mt-1 space-y-1 border-l border-border/80 pl-3"
              :aria-label="`${item.label}二级导航`"
            >
              <RouterLink
                v-for="section in sectionsForPath(item.path)"
                :key="section.to"
                :to="section.to"
                class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                exact-active-class="bg-secondary text-foreground"
              >
                <component :is="section.icon" class="size-3.5 shrink-0" aria-hidden="true" />
                <span>{{ section.label }}</span>
              </RouterLink>
            </nav>
          </div>
        </nav>
      </section>
    </div>
  </aside>

  <div v-else class="lg:hidden">
    <Sheet>
      <SheetTrigger as-child>
        <Button variant="outline" size="sm" class="rounded-full">
          <Menu class="size-4" aria-hidden="true" />后台设置
        </Button>
      </SheetTrigger>
      <SheetContent side="left" class="w-[88vw] max-w-sm overflow-y-auto">
        <SheetHeader class="text-left">
          <SheetTitle>后台设置导航</SheetTitle>
          <SheetDescription>选择需要进入的治理、运营或系统管理功能。</SheetDescription>
        </SheetHeader>
        <div class="mt-6 space-y-5">
          <section v-for="group in adminNavigationGroups" :key="group">
            <h3 class="px-2 text-xs font-semibold text-muted-foreground">{{ group }}</h3>
            <nav class="mt-2 space-y-1" :aria-label="`${group}移动导航`">
              <div v-for="item in itemsForGroup(group)" :key="item.path">
                <SheetClose as-child>
                  <RouterLink
                    :to="item.path"
                    class="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    exact-active-class="bg-primary text-primary-foreground"
                  >
                    <component :is="item.icon" class="size-4 shrink-0" aria-hidden="true" />
                    <span>{{ item.label }}</span>
                  </RouterLink>
                </SheetClose>

                <nav
                  v-if="sectionsForPath(item.path).length > 0"
                  class="ml-5 mt-1 space-y-1 border-l border-border/80 pl-3"
                  :aria-label="`${item.label}移动二级导航`"
                >
                  <SheetClose v-for="section in sectionsForPath(item.path)" :key="section.to" as-child>
                    <RouterLink
                      :to="section.to"
                      class="flex items-center gap-2 rounded-lg px-2.5 py-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      exact-active-class="bg-secondary text-foreground"
                    >
                      <component :is="section.icon" class="size-3.5 shrink-0" aria-hidden="true" />
                      <span>{{ section.label }}</span>
                    </RouterLink>
                  </SheetClose>
                </nav>
              </div>
            </nav>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  </div>
</template>
