<script setup lang="ts">
import { ArrowLeft, ArrowRight, CircleHelp, X } from "lucide-vue-next";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

const COMPLETED_KEY = "web-onboarding-completed-v1";
const DISMISSED_KEY = "web-onboarding-dismissed-v1";
const SKIPPED_KEY = "web-onboarding-skipped-v1";

interface TourStep {
  title: string;
  description: string;
  to: string;
  actionLabel: string;
}

const steps: readonly TourStep[] = [
  {
    title: "本地计算优先",
    description: "压缩包指纹、文本摘要和文件摘要都可以在浏览器内处理，原始内容不上传服务器。",
    to: "/",
    actionLabel: "回到首页",
  },
  {
    title: "社区公开协作",
    description: "在公开社区交流授权恢复经验。用户资料和私密内容不会作为公开搜索或 SEO 内容展示。",
    to: "/community",
    actionLabel: "查看社区",
  },
  {
    title: "使用安全工具",
    description: "通用哈希计算器和随机密码生成器只在当前浏览器工作，不保存输入和生成历史。",
    to: "/tools",
    actionLabel: "打开工具",
  },
];

const props = withDefaults(
  defineProps<{
    initialOpen?: boolean;
    autoOpen?: boolean;
  }>(),
  {
    initialOpen: false,
    autoOpen: true,
  },
);

const open = ref(props.initialOpen);
const currentStep = ref(0);
const heading = ref<HTMLElement | null>(null);

function openTour(): void {
  currentStep.value = 0;
  open.value = true;
}

function closeForSession(): void {
  if (typeof window !== "undefined") window.sessionStorage.setItem(SKIPPED_KEY, "1");
  open.value = false;
}

function dismissPermanently(): void {
  if (typeof window !== "undefined") window.localStorage.setItem(DISMISSED_KEY, "1");
  open.value = false;
}

function previousStep(): void {
  currentStep.value = Math.max(0, currentStep.value - 1);
}

function nextStep(): void {
  if (currentStep.value >= steps.length - 1) {
    if (typeof window !== "undefined") window.localStorage.setItem(COMPLETED_KEY, "1");
    open.value = false;
    return;
  }
  currentStep.value += 1;
}

function handleKeydown(event: KeyboardEvent): void {
  if (!open.value) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeForSession();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    previousStep();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    nextStep();
  }
}

async function focusHeading(): Promise<void> {
  await nextTick();
  heading.value?.focus();
}

watch([open, currentStep], () => {
  if (open.value) void focusHeading();
});

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
  if (!props.autoOpen || props.initialOpen) return;
  const hasCompleted = window.localStorage.getItem(COMPLETED_KEY) === "1";
  const hasDismissed = window.localStorage.getItem(DISMISSED_KEY) === "1";
  const hasSkipped = window.sessionStorage.getItem(SKIPPED_KEY) === "1";
  if (!hasCompleted && !hasDismissed && !hasSkipped) openTour();
});

onBeforeUnmount(() => window.removeEventListener("keydown", handleKeydown));

defineExpose<{ open: () => void }>({ open: openTour });
</script>

<template>
  <aside
    v-if="open"
    class="fixed bottom-4 left-4 z-40 w-[calc(100%-2rem)] max-w-md sm:bottom-6 sm:left-6"
    role="dialog"
    aria-modal="false"
    aria-labelledby="onboarding-tour-title"
    aria-describedby="onboarding-tour-description"
  >
    <Card class="border-primary/20 bg-card/95 shadow-2xl backdrop-blur">
      <CardHeader class="flex-row items-start gap-3 space-y-0 pb-3">
        <span class="rounded-full bg-primary/10 p-2 text-primary" aria-hidden="true"><CircleHelp class="size-4" /></span>
        <div class="min-w-0 flex-1">
          <p class="text-xs font-medium text-muted-foreground">新手引导 · 第 {{ currentStep + 1 }} / {{ steps.length }} 步</p>
          <div ref="heading" tabindex="-1" class="outline-none">
            <CardTitle id="onboarding-tour-title" class="mt-1 text-base leading-6">{{ steps[currentStep].title }}</CardTitle>
          </div>
        </div>
        <Button variant="ghost" size="icon" type="button" aria-label="暂时关闭新手引导" @click="closeForSession"><X class="size-4" /></Button>
      </CardHeader>
      <CardContent>
        <p id="onboarding-tour-description" class="text-sm leading-6 text-muted-foreground">{{ steps[currentStep].description }}</p>
        <Button variant="link" size="sm" class="mt-2 h-auto px-0" as-child><RouterLink :to="steps[currentStep].to">{{ steps[currentStep].actionLabel }}</RouterLink></Button>
      </CardContent>
      <CardFooter class="flex flex-wrap items-center justify-between gap-2 border-t bg-muted/20 py-3">
        <div class="flex items-center gap-1">
          <Button variant="ghost" size="sm" type="button" :disabled="currentStep === 0" @click="previousStep"><ArrowLeft class="size-4" />上一步</Button>
          <Button size="sm" type="button" @click="nextStep">{{ currentStep === steps.length - 1 ? "完成" : "下一步" }}<ArrowRight v-if="currentStep < steps.length - 1" class="size-4" /></Button>
        </div>
        <div class="flex items-center gap-1">
          <Button variant="ghost" size="sm" type="button" @click="closeForSession">跳过</Button>
          <Button variant="ghost" size="sm" type="button" @click="dismissPermanently">不再提示</Button>
        </div>
      </CardFooter>
    </Card>
  </aside>
</template>
