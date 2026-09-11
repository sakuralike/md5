<script setup lang="ts">
import type { User } from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Award, Bell, Bookmark, Code2, FileArchive, Gift, History, LockKeyhole, ShieldCheck, UserRound } from "lucide-vue-next";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { loadTrustCenter, type TrustCenterData } from "../services/reputation";
import { useCommunityAvatar } from "../composables/useCommunityAvatar";
import { useAuthStore } from "../stores/auth";

interface CenterLink {
  title: string;
  description: string;
  to: string;
  icon: typeof UserRound;
}

const auth = useAuthStore();
const communityAvatar = useCommunityAvatar();
const currentAvatarSrc = communityAvatar.avatarSrc;
const data = ref<TrustCenterData | null>(null);
const loading = ref(true);
const error = ref("");

const user = computed<User | null>(() => auth.user);
const initials = computed(() => user.value?.username.slice(0, 1).toUpperCase() ?? "?");
const centerLinks: CenterLink[] = [
  { title: "个人资料", description: "编辑社区公开资料与头像信息", to: "/community/settings", icon: UserRound },
  { title: "开发者应用", description: "创建、修改并提交第三方桌面应用申请", to: "/developer/applications", icon: Code2 },
  { title: "账号安全", description: "密码、TOTP 与登录会话管理", to: "/security", icon: ShieldCheck },
  { title: "等级积分信誉", description: "查看成长值、积分流水与信誉事件", to: "/reputation", icon: Award },
  { title: "邀请奖励", description: "分享专属链接并查看邀请积分", to: "/referrals", icon: Gift },
  { title: "我的贡献", description: "跟踪提交记录与审核结果", to: "/submissions", icon: FileArchive },
  { title: "我的收藏", description: "快速访问收藏的社区内容", to: "/community/bookmarks", icon: Bookmark },
  { title: "社区通知", description: "处理提及、回复与治理通知", to: "/community/notifications", icon: Bell },
  { title: "活动记录", description: "回顾账号登录与关键操作", to: "/account/activity", icon: History },
  { title: "隐私中心", description: "管理公开范围与数据导出", to: "/account/privacy", icon: LockKeyhole },
];

const reputationPercent = computed(() => {
  const profile = data.value?.profile;
  if (!profile) return 0;
  const range = profile.reputation_max - profile.reputation_min;
  return range > 0 ? ((profile.reputation_score - profile.reputation_min) / range) * 100 : 0;
});

async function load(): Promise<void> {
  if (!auth.accessToken) {
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    data.value = await loadTrustCenter(auth.accessToken);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "等级与信誉信息暂时无法加载";
  } finally {
    loading.value = false;
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value));
}

onMounted(() => {
  void load();
  if (auth.user && auth.accessToken) void communityAvatar.hydrate(auth.user.id, auth.accessToken);
});
</script>

<template>
  <section class="mx-auto grid max-w-6xl gap-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div class="eyebrow">PERSONAL WORKSPACE</div>
        <h1 class="page-title">用户中心</h1>
        <p class="lead">从这里管理你的资料、安全设置、社区互动与贡献记录。</p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load">{{ loading ? "同步中…" : "刷新数据" }}</Button>
    </div>

    <Card class="glass overflow-hidden rounded-[2rem]">
      <CardContent class="grid gap-6 p-6 sm:grid-cols-[auto_1fr] sm:items-center sm:p-8">
        <Avatar size="base" class="h-24 w-24 border-4 border-background shadow-lg sm:h-28 sm:w-28">
          <AvatarImage v-if="currentAvatarSrc" :src="currentAvatarSrc" :alt="`${user?.username ?? '用户'} 的头像`" />
          <AvatarFallback class="bg-gradient-to-br from-primary to-accent text-3xl font-bold text-primary-foreground">
            {{ initials }}
          </AvatarFallback>
        </Avatar>
        <div class="grid gap-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p class="text-2xl font-bold tracking-tight">{{ user?.username }}</p>
              <p class="text-sm text-muted-foreground">{{ user?.email }}</p>
              <p class="mt-1 font-mono text-xs text-muted-foreground">UID：{{ user?.uid ?? user?.id ?? "—" }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <Badge variant="secondary">{{ user?.role === "admin" ? "管理员" : "社区成员" }}</Badge>
              <Badge :variant="user?.email_verified ? 'default' : 'outline'">
                {{ user?.email_verified ? "邮箱已验证" : "邮箱待验证" }}
              </Badge>
              <Badge variant="outline">{{ user?.totp_enabled ? "TOTP 已启用" : "TOTP 未启用" }}</Badge>
            </div>
          </div>
          <Separator />
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <span class="text-xs text-muted-foreground">用户 UID</span>
              <strong class="mt-1 block break-all font-mono text-xs">{{ user?.uid ?? user?.id ?? "—" }}</strong>
            </div>
            <div>
              <span class="text-xs text-muted-foreground">注册时间</span>
              <strong class="mt-1 block text-sm">{{ user ? formatDate(user.created_at) : "—" }}</strong>
            </div>
            <div>
              <span class="text-xs text-muted-foreground">当前信誉分</span>
              <strong class="mt-1 block text-sm">{{ data?.profile.reputation_score ?? user?.reputation_score ?? "—" }}</strong>
            </div>
            <div>
              <span class="text-xs text-muted-foreground">当前等级</span>
              <strong class="mt-1 block text-sm">{{ data?.profile.level.current.name ?? "加载中" }}</strong>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-4 sm:grid-cols-3">
      <Card class="glass rounded-3xl">
        <CardHeader class="pb-3"><CardDescription>成长值</CardDescription><CardTitle>{{ data?.profile.level.growth_points ?? "—" }}</CardTitle></CardHeader>
        <CardContent><Progress :model-value="data?.profile.level.progress_percent ?? 0" aria-label="等级成长进度" /></CardContent>
      </Card>
      <Card class="glass rounded-3xl">
        <CardHeader class="pb-3"><CardDescription>可用积分</CardDescription><CardTitle>{{ data?.profile.points.available ?? "—" }}</CardTitle></CardHeader>
        <CardContent><p class="text-sm text-muted-foreground">{{ data ? `待结算 ${data.profile.points.pending} · 已冲正 ${data.profile.points.reversed}` : "正在同步账户数据" }}</p></CardContent>
      </Card>
      <Card class="glass rounded-3xl">
        <CardHeader class="pb-3"><CardDescription>信誉进度</CardDescription><CardTitle>{{ data ? `${data.profile.reputation_score} / ${data.profile.reputation_max}` : "—" }}</CardTitle></CardHeader>
        <CardContent><Progress :model-value="reputationPercent" aria-label="信誉分进度" /></CardContent>
      </Card>
    </div>

    <p v-if="error" class="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>

    <div>
      <div class="mb-4 flex items-center justify-between gap-3">
        <div><h2 class="text-xl font-semibold">快捷入口</h2><p class="text-sm text-muted-foreground">将原先分散在导航栏的账号能力集中到一个工作台。</p></div>
      </div>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card v-for="item in centerLinks" :key="item.to" class="glass group rounded-3xl transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg">
          <CardHeader class="gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary"><component :is="item.icon" class="h-5 w-5" /></div>
            <CardTitle class="text-base">{{ item.title }}</CardTitle>
            <CardDescription>{{ item.description }}</CardDescription>
          </CardHeader>
          <CardContent><Button variant="ghost" class="w-full justify-start px-0 text-primary" as-child><RouterLink :to="item.to">打开 {{ item.title }} →</RouterLink></Button></CardContent>
        </Card>
      </div>
    </div>
  </section>
</template>

