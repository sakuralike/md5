<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import type { SwitchRootEmits, SwitchRootProps } from "reka-ui"
import { reactiveOmit } from "@vueuse/core"
import { SwitchRoot, SwitchThumb, useForwardPropsEmits } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<SwitchRootProps & { class?: HTMLAttributes["class"] }>()
const emits = defineEmits<SwitchRootEmits>()
const forwarded = useForwardPropsEmits(reactiveOmit(props, "class"), emits)
</script>

<template>
  <SwitchRoot v-bind="forwarded" :class="cn('peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent bg-muted transition-colors data-[state=checked]:bg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50', props.class)">
    <SwitchThumb class="pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0" />
  </SwitchRoot>
</template>
