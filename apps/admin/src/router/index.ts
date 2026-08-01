import { createRouter, createWebHistory } from "vue-router";
import AuditPage from "../pages/AuditPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import LoginPage from "../pages/LoginPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginPage },
    { path: "/", component: DashboardPage, meta: { requiresAdmin: true } },
    { path: "/audit", component: AuditPage, meta: { requiresAdmin: true } },
  ],
});

router.beforeEach((to) => {
  if (to.meta.requiresAdmin && !sessionStorage.getItem("password_detective_admin_session_v1")) {
    return "/login";
  }
  return true;
});

export default router;
