import { createRouter, createWebHistory } from "vue-router";
import HomePage from "../pages/HomePage.vue";
import LoginPage from "../pages/LoginPage.vue";
import RegisterPage from "../pages/RegisterPage.vue";
import ReputationPage from "../pages/ReputationPage.vue";
import SecurityPage from "../pages/SecurityPage.vue";
import SubmissionsPage from "../pages/SubmissionsPage.vue";
import TrustCasesPage from "../pages/TrustCasesPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage },
    { path: "/login", component: LoginPage, meta: { guestOnly: true } },
    { path: "/register", component: RegisterPage, meta: { guestOnly: true } },
    { path: "/security", component: SecurityPage, meta: { requiresAuth: true } },
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
