import { createRouter, createWebHistory } from "vue-router";
import AuditPage from "../pages/AuditPage.vue";
import CandidateModerationPage from "../pages/CandidateModerationPage.vue";
import CommunityConfigurationPage from "../pages/CommunityConfigurationPage.vue";
import CommunityModerationPage from "../pages/CommunityModerationPage.vue";
import CommunityNotificationOutboxPage from "../pages/CommunityNotificationOutboxPage.vue";
import CommunitySearchHealthPage from "../pages/CommunitySearchHealthPage.vue";
import DataHeatmapPage from "../pages/DataHeatmapPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import DesktopReleasesPage from "../pages/DesktopReleasesPage.vue";
import DesktopAnnouncementsPage from "../pages/DesktopAnnouncementsPage.vue";
import WebAnnouncementsPage from "../pages/WebAnnouncementsPage.vue";
import HashPoolPage from "../pages/HashPoolPage.vue";
import LoginPage from "../pages/LoginPage.vue";
import RiskAlertsPage from "../pages/RiskAlertsPage.vue";
import RewardCatalogPage from "../pages/RewardCatalogPage.vue";
import RewardOrdersPage from "../pages/RewardOrdersPage.vue";
import RegistrationSettingsPage from "../pages/RegistrationSettingsPage.vue";
import RoleChangesPage from "../pages/RoleChangesPage.vue";
import PluginReviewsPage from "../pages/PluginReviewsPage.vue";
import SystemSettingsPage from "../pages/SystemSettingsPage.vue";
import TotpSetupPage from "../pages/TotpSetupPage.vue";
import TrustCasesPage from "../pages/TrustCasesPage.vue";
import ThirdPartyAppsPage from "../pages/ThirdPartyAppsPage.vue";
import UserGovernancePage from "../pages/UserGovernancePage.vue";

const STORAGE_KEY = "password_detective_admin_session_v2";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition;
    if (to.hash) return { el: to.hash, top: 104, behavior: "smooth" };
    return { top: 0 };
  },
  routes: [
    { path: "/login", component: LoginPage },
    { path: "/totp-setup", component: TotpSetupPage, meta: { requiresAdmin: true } },
    { path: "/", component: DashboardPage, meta: { requiresAdmin: true } },
    { path: "/audit", component: AuditPage, meta: { requiresAdmin: true } },
    { path: "/users", component: UserGovernancePage, meta: { requiresAdmin: true } },
    { path: "/registration", component: RegistrationSettingsPage, meta: { requiresAdmin: true } },
    { path: "/role-changes", component: RoleChangesPage, meta: { requiresAdmin: true } },
    { path: "/settings", component: SystemSettingsPage, meta: { requiresAdmin: true } },
    { path: "/candidates", component: CandidateModerationPage, meta: { requiresAdmin: true } },
    { path: "/hash-pool", component: HashPoolPage, meta: { requiresAdmin: true } },
    { path: "/trust-cases", component: TrustCasesPage, meta: { requiresAdmin: true } },
    { path: "/third-party-apps", component: ThirdPartyAppsPage, meta: { requiresAdmin: true } },
    { path: "/plugin-reviews", component: PluginReviewsPage, meta: { requiresAdmin: true } },
    { path: "/community", component: CommunityModerationPage, meta: { requiresAdmin: true } },
    { path: "/community/settings", component: CommunityConfigurationPage, meta: { requiresAdmin: true } },
    { path: "/community/notifications", component: CommunityNotificationOutboxPage, meta: { requiresAdmin: true } },
    { path: "/community/search-health", component: CommunitySearchHealthPage, meta: { requiresAdmin: true } },
    { path: "/analytics/heatmap", component: DataHeatmapPage, meta: { requiresAdmin: true } },
    { path: "/risk-alerts", component: RiskAlertsPage, meta: { requiresAdmin: true } },
    { path: "/rewards/catalog", component: RewardCatalogPage, meta: { requiresAdmin: true } },
    { path: "/rewards/orders", component: RewardOrdersPage, meta: { requiresAdmin: true } },
    { path: "/desktop-releases", component: DesktopReleasesPage, meta: { requiresAdmin: true } },
    { path: "/desktop-announcements", component: DesktopAnnouncementsPage, meta: { requiresAdmin: true } },
    { path: "/web-announcements", component: WebAnnouncementsPage, meta: { requiresAdmin: true } },
  ],
});

interface RoutedAdminSession {
  accessToken?: string;
}

function readSession(): RoutedAdminSession | null {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as RoutedAdminSession;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

router.beforeEach((to) => {
  const session = readSession();
  if (to.meta.requiresAdmin && !session?.accessToken) return "/login";
  return true;
});

export default router;
