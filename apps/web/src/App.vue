<script setup lang="ts">
import type { PublicSiteConfig } from "@password-detective/api-contract";
import { CircleHelp } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import AnnouncementPopup from "./components/AnnouncementPopup.vue";
import AppBreadcrumbs from "./components/AppBreadcrumbs.vue";
import MaintenancePage from "./components/MaintenancePage.vue";
import OnboardingTour from "./components/OnboardingTour.vue";
import UserAccountMenu from "./components/UserAccountMenu.vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { provideCommunitySeo } from "./composables/useCommunitySeo";
import { useCommunityAvatar } from "./composables/useCommunityAvatar";
import { useCommunityDirectMessageStream } from "./composables/useCommunityDirectMessageStream";
import { useCommunityNotificationStream } from "./composables/useCommunityNotificationStream";
import { applySeoMetadata, buildSeoMetadata, type SeoRouteScope } from "./lib/seo";
import { createDefaultPublicSiteConfig, getPublicSiteConfig } from "./services/site";
import { useRoute } from "vue-router";
import { useAuthStore } from "./stores/auth";

type BackgroundPreset = "frost" | "grid" | "aurora" | "halo" | "custom";

interface BackgroundOption {
  id: Exclude<BackgroundPreset, "custom">;
  name: string;
  description: string;
}

const auth = useAuthStore();
const route = useRoute();
const communityNotifications = useCommunityNotificationStream();
const communityDirectMessages = useCommunityDirectMessageStream();
const communityAvatar = useCommunityAvatar();
const communitySeo = provideCommunitySeo();
const currentAvatarSrc = communityAvatar.avatarSrc;
const siteConfig = ref<PublicSiteConfig>(createDefaultPublicSiteConfig());
const onboardingTour = ref<{ open: () => void } | null>(null);

const visibleNavigation = computed(() =>
  siteConfig.value.navigation.filter((item) => !item.requires_auth || auth.isAuthenticated),
);
const hasToolsNavigation = computed(() => visibleNavigation.value.some((item) => item.path === "/tools"));

function applyCurrentSeo(): void {
  if (typeof document === "undefined" || typeof window === "undefined") return;
  const contentState = communitySeo.current.value;
  const contentKind = route.meta.seoContent;
  const community = contentState
    && contentKind
    && contentState.kind === contentKind
    && contentState.path === route.path
    ? { kind: contentKind, projection: contentState.projection }
    : undefined;
  applySeoMetadata(
    document,
    buildSeoMetadata({
      path: route.path,
      seo: siteConfig.value.seo,
      siteName: siteConfig.value.site_name,
      origin: window.location.origin,
      scope: route.meta.seoScope as SeoRouteScope | undefined,
      title: typeof route.meta.seoTitle === "string" ? route.meta.seoTitle : undefined,
      community,
    }),
    siteConfig.value.site_name,
  );
}

async function loadSiteConfig(): Promise<void> {
  try {
    siteConfig.value = await getPublicSiteConfig();
  } catch {
    // 公共配置不可用时继续使用内置安全默认值。
  }
}

const backgroundOptions: BackgroundOption[] = [
  { id: "frost", name: "冰川白", description: "清透蓝白光晕" },
  { id: "grid", name: "数据网格", description: "极简科技网格" },
  { id: "aurora", name: "极光雾", description: "青紫柔光渐变" },
  { id: "halo", name: "晨曦环", description: "暖白能量光环" },
];
const savedBackground = localStorage.getItem("web-background-preset");
const activeBackground = ref<BackgroundPreset>(
  backgroundOptions.some((item) => item.id === savedBackground) ? (savedBackground as BackgroundPreset) : "frost",
);
const backgroundPanelOpen = ref(false);
const customBackgroundUrl = ref("");
const backgroundError = ref("");

function selectBackground(id: BackgroundOption["id"]): void {
  releaseCustomBackground();
  activeBackground.value = id;
  localStorage.setItem("web-background-preset", id);
  backgroundError.value = "";
  backgroundPanelOpen.value = false;
}

function uploadBackground(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    backgroundError.value = "请选择图片文件。";
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    backgroundError.value = "背景图片不能超过 10 MiB。";
    return;
  }
  releaseCustomBackground();
  customBackgroundUrl.value = URL.createObjectURL(file);
  activeBackground.value = "custom";
  localStorage.removeItem("web-background-preset");
  backgroundError.value = "";
  backgroundPanelOpen.value = false;
}

function resetBackground(): void {
  selectBackground("frost");
}

function releaseCustomBackground(): void {
  if (customBackgroundUrl.value) {
    URL.revokeObjectURL(customBackgroundUrl.value);
    customBackgroundUrl.value = "";
  }
}

onMounted(() => {
  watch(
    () => [
      route.path,
      route.meta.seoScope,
      route.meta.seoTitle,
      route.meta.seoContent,
      siteConfig.value,
      communitySeo.current.value,
    ] as const,
    applyCurrentSeo,
    { immediate: true },
  );
  void loadSiteConfig();
  watch(
    () => [auth.isAuthenticated, auth.user?.id ?? "", auth.accessToken] as const,
    ([isAuthenticated, userId, accessToken]) => {
      if (!isAuthenticated || !userId || !accessToken) {
        communityAvatar.clear();
        return;
      }
      void communityAvatar.hydrate(userId, accessToken);
    },
    { immediate: true },
  );
});
onBeforeUnmount(releaseCustomBackground);
</script>

<template>
  <div class="shell" :data-background="activeBackground">
    <MaintenancePage
      v-if="siteConfig.maintenance.active"
      :site-name="siteConfig.site_name"
      :site-logo-url="siteConfig.site_logo_url"
      :contact-email="siteConfig.legal.public_contact_email"
      :maintenance="siteConfig.maintenance"
    />
    <template v-else>
    <a
      href="#main-content"
      class="sr-only z-50 rounded-md bg-background px-4 py-2 text-foreground shadow-lg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
    >
      跳到主要内容
    </a>
    <div
      class="ambient-background"
      :class="{ 'ambient-background-custom': activeBackground === 'custom' }"
      aria-hidden="true"
    >
      <img
        v-if="activeBackground === 'custom' && customBackgroundUrl"
        :src="customBackgroundUrl"
        alt=""
        class="absolute inset-0 h-full w-full object-cover opacity-40"
      />
      <span class="ambient-orb ambient-orb-one"></span>
      <span class="ambient-orb ambient-orb-two"></span>
      <span class="ambient-grid"></span>
    </div>

    <header class="topbar">
      <RouterLink class="brand" to="/" :aria-label="`${siteConfig.site_name}首页`">
        <img v-if="siteConfig.site_logo_url" :src="siteConfig.site_logo_url" alt="" class="h-11 w-11 rounded-2xl object-contain shadow-sm" />
        <span v-else class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="img">
            <path d="m15.5 15.5 4 4" />
            <circle cx="10.5" cy="10.5" r="5.5" />
            <path d="M8.25 10.5h4.5M10.5 8.25v4.5" />
          </svg>
        </span>
        <span class="brand-copy">
          <strong>{{ siteConfig.site_name }}</strong>
          <small>TRUSTED ARCHIVE LAB</small>
        </span>
      </RouterLink>

      <nav class="nav" aria-label="主导航">
        <RouterLink v-for="item in visibleNavigation" :key="item.path" :to="item.path">{{ item.label }}</RouterLink>
        <RouterLink v-if="!hasToolsNavigation" to="/tools">安全工具</RouterLink>
      </nav>

      <div class="topbar-actions">
        <Button
          variant="ghost"
          size="icon"
          type="button"
          title="打开新手引导"
          aria-label="打开新手引导"
          @click="onboardingTour?.open()"
        >
          <CircleHelp class="size-4" />
        </Button>
        <div class="background-control">
          <Button
            class="icon-button"
            type="button"
            :aria-expanded="backgroundPanelOpen"
            aria-controls="background-panel"
            title="更换页面背景"
            @click="backgroundPanelOpen = !backgroundPanelOpen"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3a9 9 0 1 0 9 9c0-1.1-.9-2-2-2h-1.2a2 2 0 0 1-2-2V6.8A3.8 3.8 0 0 0 12 3Z" />
              <circle cx="7.5" cy="11" r="1" />
              <circle cx="10" cy="7" r="1" />
              <circle cx="8.5" cy="15" r="1" />
            </svg>
            <span>背景</span>
          </Button>

          <section v-if="backgroundPanelOpen" id="background-panel" class="background-panel" aria-label="背景选择">
            <div class="background-panel-heading">
              <div>
                <strong>空间背景</strong>
                <small>选择预设或上传本地图片</small>
              </div>
              <Button class="panel-close" type="button" aria-label="关闭背景选择" @click="backgroundPanelOpen = false">×</Button>
            </div>
            <div class="background-options">
              <Button
                v-for="option in backgroundOptions"
                :key="option.id"
                class="background-option"
                :class="[`background-preview-${option.id}`, { active: activeBackground === option.id }]"
                type="button"
                @click="selectBackground(option.id)"
              >
                <span class="background-swatch" aria-hidden="true"></span>
                <span><strong>{{ option.name }}</strong><small>{{ option.description }}</small></span>
                <span v-if="activeBackground === option.id" class="option-check" aria-hidden="true">✓</span>
              </Button>
            </div>
            <div class="background-panel-actions">
              <label class="upload-background">
                <Input type="file" accept="image/*" @change="uploadBackground" />
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
                </svg>
                上传本地图片
              </label>
              <Button class="reset-background" type="button" @click="resetBackground">恢复默认</Button>
            </div>
            <p v-if="backgroundError" class="background-error">{{ backgroundError }}</p>
            <small class="background-privacy">图片仅在当前浏览器会话中显示，不会上传。</small>
          </section>
        </div>

        <div v-if="!auth.isAuthenticated" class="flex items-center gap-2">
          <Button variant="ghost" size="sm" as-child>
            <RouterLink to="/login">登录</RouterLink>
          </Button>
          <Button size="sm" as-child>
            <RouterLink to="/register">注册</RouterLink>
          </Button>
        </div>
        <UserAccountMenu
          v-else-if="auth.user"
          :user="auth.user"
          :busy="auth.busy"
          :avatar-src="currentAvatarSrc"
          :unread-count="communityNotifications.unreadCount.value"
          :notification-status="communityNotifications.status.value"
          :direct-unread-count="communityDirectMessages.totalUnreadCount.value"
          :direct-message-status="communityDirectMessages.status.value"
          @logout="auth.logout()"
        />
      </div>
    </header>

    <main id="main-content" class="main" tabindex="-1">
      <AppBreadcrumbs />
      <RouterView />
    </main>

    <AnnouncementPopup />
    <OnboardingTour ref="onboardingTour" />

    <footer class="site-footer">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span>{{ siteConfig.legal.copyright_text || `${siteConfig.site_name} · 隐私优先的压缩包指纹协作平台` }}</span>
        <a v-if="siteConfig.legal.icp_record" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" class="hover:text-foreground hover:underline">{{ siteConfig.legal.icp_record }}</a>
        <a v-if="siteConfig.legal.public_security_record" href="https://beian.mps.gov.cn/#/query/webSearch" target="_blank" rel="noopener noreferrer" class="hover:text-foreground hover:underline">{{ siteConfig.legal.public_security_record }}</a>
        <a v-if="siteConfig.legal.public_contact_email" :href="`mailto:${siteConfig.legal.public_contact_email}`" class="hover:text-foreground hover:underline">{{ siteConfig.legal.public_contact_email }}</a>
      </div>
      <span class="system-status"><i aria-hidden="true"></i> 本地计算模式</span>
    </footer>
    </template>
  </div>
</template>
