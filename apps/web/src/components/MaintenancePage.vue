<script setup lang="ts">
import type { PublicMaintenanceConfig } from "@password-detective/api-contract";
import { Mail, Wrench } from "lucide-vue-next";

defineProps<{
  siteName: string;
  siteLogoUrl: string;
  contactEmail: string;
  maintenance: PublicMaintenanceConfig;
}>();
</script>

<template>
  <main class="relative z-10 flex min-h-screen items-center justify-center px-5 py-16">
    <div class="w-full max-w-2xl text-center">
      <img v-if="siteLogoUrl" :src="siteLogoUrl" alt="" class="mx-auto mb-6 size-16 object-contain" />
      <div v-else class="mx-auto mb-6 flex size-16 items-center justify-center rounded-full border border-border bg-background text-primary shadow-sm">
        <Wrench class="size-7" aria-hidden="true" />
      </div>
      <p class="text-sm font-medium text-primary">{{ siteName }}</p>
      <h1 class="mt-3 text-3xl font-semibold text-foreground sm:text-4xl">系统维护中</h1>
      <p class="mx-auto mt-5 max-w-xl whitespace-pre-line text-base leading-7 text-muted-foreground">{{ maintenance.message }}</p>
      <a v-if="contactEmail" :href="`mailto:${contactEmail}`" class="mt-8 inline-flex items-center gap-2 text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        <Mail class="size-4" aria-hidden="true" />{{ contactEmail }}
      </a>
    </div>
  </main>
</template>
