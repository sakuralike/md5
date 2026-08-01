import { createRouter, createWebHistory } from "vue-router";
import HomePage from "../pages/HomePage.vue";
import LoginPage from "../pages/LoginPage.vue";
import RegisterPage from "../pages/RegisterPage.vue";
import SecurityPage from "../pages/SecurityPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage },
    { path: "/login", component: LoginPage, meta: { guestOnly: true } },
    { path: "/register", component: RegisterPage, meta: { guestOnly: true } },
    { path: "/security", component: SecurityPage, meta: { requiresAuth: true } },
  ],
});

router.beforeEach((to) => {
  const authenticated = Boolean(sessionStorage.getItem("password_detective_session_v1"));
  if (to.meta.requiresAuth && !authenticated) return "/login";
  if (to.meta.guestOnly && authenticated) return "/";
  return true;
});

export default router;
