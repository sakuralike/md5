import { createRouter, createWebHistory } from "vue-router";
import AccountActivityPage from "../pages/AccountActivityPage.vue";
import AccountPrivacyPage from "../pages/AccountPrivacyPage.vue";
import ForgotPasswordPage from "../pages/ForgotPasswordPage.vue";
import HomePage from "../pages/HomePage.vue";
import LoginPage from "../pages/LoginPage.vue";
import RegisterPage from "../pages/RegisterPage.vue";
import ResetPasswordPage from "../pages/ResetPasswordPage.vue";
import ReputationPage from "../pages/ReputationPage.vue";
import SecurityPage from "../pages/SecurityPage.vue";
import SubmissionsPage from "../pages/SubmissionsPage.vue";
import TrustCasesPage from "../pages/TrustCasesPage.vue";
import VerifyEmailPage from "../pages/VerifyEmailPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage },
    { path: "/login", component: LoginPage, meta: { guestOnly: true } },
    { path: "/register", component: RegisterPage, meta: { guestOnly: true } },
    { path: "/forgot-password", component: ForgotPasswordPage, meta: { guestOnly: true } },
    { path: "/reset-password", component: ResetPasswordPage },
    { path: "/verify-email", component: VerifyEmailPage },
    { path: "/security", component: SecurityPage, meta: { requiresAuth: true } },
    { path: "/account/profile", redirect: "/security" },
    { path: "/account/activity", component: AccountActivityPage, meta: { requiresAuth: true } },
    { path: "/account/privacy", component: AccountPrivacyPage, meta: { requiresAuth: true } },
    { path: "/submissions", component: SubmissionsPage, meta: { requiresAuth: true } },
    { path: "/reputation", component: ReputationPage, meta: { requiresAuth: true } },
    { path: "/trust-cases", component: TrustCasesPage, meta: { requiresAuth: true } },
  ],
});

router.beforeEach((to) => {
  const authenticated = Boolean(sessionStorage.getItem("password_detective_session_v2"));
  if (to.meta.requiresAuth && !authenticated) return "/login";
  if (to.meta.guestOnly && authenticated) return "/";
  return true;
});

export default router;
