import { createRouter, createWebHistory } from "vue-router";
import AuditPage from "../pages/AuditPage.vue";
import CandidateModerationPage from "../pages/CandidateModerationPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import DesktopReleasesPage from "../pages/DesktopReleasesPage.vue";
import LoginPage from "../pages/LoginPage.vue";
import RiskAlertsPage from "../pages/RiskAlertsPage.vue";
import TotpSetupPage from "../pages/TotpSetupPage.vue";
import TrustCasesPage from "../pages/TrustCasesPage.vue";
import UserGovernancePage from "../pages/UserGovernancePage.vue";

const STORAGE_KEY = "password_detective_admin_session_v2";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginPage },
    { path: "/totp-setup", component: TotpSetupPage, meta: { requiresEnrollment: true } },
    { path: "/", component: DashboardPage, meta: { requiresAdmin: true } },
    { path: "/audit", component: AuditPage, meta: { requiresAdmin: true } },
    { path: "/users", component: UserGovernancePage, meta: { requiresAdmin: true } },
    { path: "/candidates", component: CandidateModerationPage, meta: { requiresAdmin: true } },
    { path: "/trust-cases", component: TrustCasesPage, meta: { requiresAdmin: true } },
    { path: "/risk-alerts", component: RiskAlertsPage, meta: { requiresAdmin: true } },
    { path: "/desktop-releases", component: DesktopReleasesPage, meta: { requiresAdmin: true } },
  ],
});

function readSession(): { enrollmentOnly?: boolean } | null {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as { enrollmentOnly?: boolean };
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

router.beforeEach((to) => {
  const session = readSession();
  if (to.meta.requiresEnrollment && (!session || !session.enrollmentOnly)) return "/login";
  if (to.meta.requiresAdmin && (!session || session.enrollmentOnly)) return "/login";
  return true;
});

export default router;
