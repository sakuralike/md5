<script setup lang="ts">
import { Moon, Sun } from "lucide-vue-next";
import { computed } from "vue";
import { toggleTheme, useTheme } from "./theme";

interface ThemeToggleProps {
  disabled?: boolean;
}

const props = withDefaults(defineProps<ThemeToggleProps>(), {
  disabled: false,
});

const { theme } = useTheme();
const isDark = computed(() => theme.value === "dark");

function handleClick(): void {
  if (props.disabled) return;
  toggleTheme();
}
</script>

<template>
  <button
    type="button"
    role="switch"
    aria-label="切换主题"
    :aria-checked="isDark"
    :disabled="props.disabled"
    title="切换主题"
    class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-border/80 bg-background/70 text-foreground shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none"
    @click="handleClick"
  >
    <Moon v-if="!isDark" class="size-4" aria-hidden="true" />
    <Sun v-else class="size-4" aria-hidden="true" />
  </button>
</template>
