<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

interface BreadcrumbEntry {
  label: string;
  to?: string;
}

const route = useRoute();

const entries = computed<BreadcrumbEntry[]>(() => {
  const path = route.path;
  if (path === "/") return [];
  if (path.startsWith("/developer/applications") || path.startsWith("/developer/apply")) {
    return [
      { label: "首页", to: "/" },
      { label: "用户中心", to: "/user-center" },
      { label: "开发者应用" },
    ];
  }
  if (path === "/user-center") return [{ label: "首页", to: "/" }, { label: "用户中心" }];
  if (path === "/community/settings") {
    return [{ label: "首页", to: "/" }, { label: "社区", to: "/community" }, { label: "社区资料与隐私" }];
  }
  if (path.startsWith("/community")) return [{ label: "首页", to: "/" }, { label: "社区" }];
  if (path === "/account/authorized-applications") {
    return [{ label: "首页", to: "/" }, { label: "用户中心", to: "/user-center" }, { label: "已授权应用" }];
  }
  if (path === "/security") return [{ label: "首页", to: "/" }, { label: "账号安全" }];
  return [{ label: "首页", to: "/" }];
});
</script>

<template>
  <nav v-if="entries.length > 0" class="mx-auto w-full max-w-6xl px-4 pt-6" aria-label="面包屑导航">
    <Breadcrumb>
      <BreadcrumbList>
        <template v-for="(entry, index) in entries" :key="`${entry.label}-${index}`">
          <BreadcrumbItem>
            <BreadcrumbLink v-if="entry.to" as-child>
              <RouterLink :to="entry.to">{{ entry.label }}</RouterLink>
            </BreadcrumbLink>
            <BreadcrumbPage v-else>{{ entry.label }}</BreadcrumbPage>
          </BreadcrumbItem>
          <BreadcrumbSeparator v-if="index < entries.length - 1" />
        </template>
      </BreadcrumbList>
    </Breadcrumb>
  </nav>
</template>
