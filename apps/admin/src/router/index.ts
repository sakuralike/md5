import { createRouter, createWebHistory } from "vue-router";
import AuditPage from "../pages/AuditPage.vue";
import CandidateModerationPage from "../pages/CandidateModerationPage.vue";
import CommunityConfigurationPage from "../pages/CommunityConfigurationPage.vue";
import CommunityModerationPage from "../pages/CommunityModerationPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import DesktopReleasesPage from "../pages/DesktopReleasesPage.vue";
import LoginPage from "../pages/LoginPage.vue";
import RiskAlertsPage from "../pages/RiskAlertsPage.vue";
import RoleChangesPage from "../pages/RoleChangesPage.vue";
import SystemSettingsPage from "../pages/SystemSettingsPage.vue";
import TotpSetupPage from "../pages/TotpSetupPage.vue";
import TrustCasesPage from "../pages/TrustCasesPage.vue";
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
    { path: "/totp-setup", component: TotpSetupPage, meta: { requiresEnrollment: true } },
    { path: "/", component: DashboardPage, meta: { requiresAdmin: true } },
    { path: "/audit", component: AuditPage, meta: { requiresAdmin: true } },
    { path: "/users", component: UserGovernancePage, meta: { requiresAdmin: true } },
    { path: "/role-changes", component: RoleChangesPage, meta: { requiresAdmin: true } },
    { path: "/settings", component: SystemSettingsPage, meta: { requiresAdmin: true } },
    { path: "/candidates", component: CandidateModerationPage, meta: { requiresAdmin: true } },
    { path: "/trust-cases", component: TrustCasesPage, meta: { requiresAdmin: true } },
    { path: "/community", component: CommunityModerationPage, meta: { requiresAdmin: true } },
    { path: "/community/settings", component: CommunityConfigurationPage, meta: { requiresAdmin: true } },
    { path: "/risk-alerts", component: RiskAlertsPage, meta: { requiresAdmin: true } },
    { path: "/desktop-releases", component: DesktopReleasesPage, meta: { requiresAdmin: true } },
  ],
});

interface RoutedAdminSession {
  enrollmentOnly?: boolean;
  user?: { totp_enabled?: boolean };
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
  const enrollmentOnly = Boolean(
    session && (session.enrollmentOnly || session.user?.totp_enabled === false),
  );
  if (to.meta.requiresEnrollment && (!session || !enrollmentOnly)) return "/login";
  if (to.meta.requiresAdmin && (!session || enrollmentOnly)) {
    return enrollmentOnly ? "/totp-setup" : "/login";
  }
  return true;
});

export default router;
