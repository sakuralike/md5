<script setup lang="ts">
import type { CommunityNotificationStreamStatus, User } from "@password-detective/api-contract";
import { computed } from "vue";
import { Bell, LogOut, UserRound } from "lucide-vue-next";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const props = withDefaults(
  defineProps<{
    user: User;
    busy?: boolean;
    defaultOpen?: boolean;
    unreadCount?: number;
    notificationStatus?: CommunityNotificationStreamStatus;
    avatarSrc?: string | null;
  }>(),
  {
    busy: false,
    defaultOpen: false,
    unreadCount: 0,
    notificationStatus: "idle",
    avatarSrc: null,
  },
);

const emit = defineEmits<{ logout: [] }>();

const initials = computed(() => props.user.username.slice(0, 1).toUpperCase());
const unreadLabel = computed(() => (props.unreadCount > 99 ? "99+" : String(props.unreadCount)));
const notificationStatusLabel = computed(() => {
  if (props.notificationStatus === "connected") return "实时连接正常";
  if (props.notificationStatus === "connecting") return "正在连接通知";
  if (props.notificationStatus === "reconnecting") return "通知正在重连";
  if (props.notificationStatus === "offline") return "通知当前离线";
  return "通知未连接";
});
</script>

<template>
  <DropdownMenu :default-open="defaultOpen">
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="h-11 w-11 rounded-full p-1 ring-offset-background transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-ring"
        :aria-label="`打开 ${user.username} 的账户菜单`"
      >
        <Avatar size="sm" class="h-9 w-9 border-2 border-background shadow-md">
          <AvatarImage v-if="avatarSrc" :src="avatarSrc" :alt="`${user.username} 的头像`" />
          <AvatarFallback class="bg-gradient-to-br from-primary to-accent text-primary-foreground font-semibold">
            {{ initials }}
          </AvatarFallback>
        </Avatar>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent
      align="end"
      side="bottom"
      :side-offset="10"
      class="w-64 rounded-2xl border-border/70 bg-popover/95 p-2 shadow-xl backdrop-blur-xl"
    >
      <DropdownMenuLabel class="px-3 py-2">
        <span class="block truncate text-sm font-semibold text-foreground">{{ user.username }}</span>
        <span class="mt-1 block truncate text-xs font-normal text-muted-foreground">{{ user.email }}</span>
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuItem as-child class="rounded-xl px-3 py-2.5">
        <RouterLink to="/user-center">
          <UserRound class="h-4 w-4" />
          <span>用户中心</span>
        </RouterLink>
      </DropdownMenuItem>
      <DropdownMenuItem as-child class="rounded-xl px-3 py-2.5">
        <RouterLink to="/community/notifications" class="flex w-full items-center gap-2">
          <Bell class="h-4 w-4" />
          <span class="flex-1">社区通知</span>
          <Badge v-if="unreadCount > 0" aria-label="未读通知数量">{{ unreadLabel }}</Badge>
          <span class="sr-only">{{ notificationStatusLabel }}</span>
        </RouterLink>
      </DropdownMenuItem>
      <DropdownMenuItem
        class="rounded-xl px-3 py-2.5 text-destructive focus:bg-destructive/10 focus:text-destructive"
        :disabled="busy"
        @select="emit('logout')"
      >
        <LogOut class="h-4 w-4" />
        <span>{{ busy ? "退出中…" : "退出登录" }}</span>
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
