import { createRouter, createWebHistory } from "vue-router";
import AccountActivityPage from "../pages/AccountActivityPage.vue";
import AccountPrivacyPage from "../pages/AccountPrivacyPage.vue";
import CommunityPage from "../pages/CommunityPage.vue";
import CommunityActivityPage from "../pages/CommunityActivityPage.vue";
import CommunityBookmarksPage from "../pages/CommunityBookmarksPage.vue";
import CommunityHomePage from "../pages/CommunityHomePage.vue";
import CommunitySearchPage from "../pages/CommunitySearchPage.vue";
import CommunityGroupsPage from "../pages/CommunityGroupsPage.vue";
import CommunityGroupPage from "../pages/CommunityGroupPage.vue";
import CommunityNotificationsPage from "../pages/CommunityNotificationsPage.vue";
import CommunityPostComposerPage from "../pages/CommunityPostComposerPage.vue";
import CommunityPostPage from "../pages/CommunityPostPage.vue";
import CommunityProfilePage from "../pages/CommunityProfilePage.vue";
import CommunityRelationsPage from "../pages/CommunityRelationsPage.vue";
import CommunitySettingsPage from "../pages/CommunitySettingsPage.vue";
import ForgotPasswordPage from "../pages/ForgotPasswordPage.vue";
import HomePage from "../pages/HomePage.vue";
import HashDetailPage from "../pages/HashDetailPage.vue";
import LoginPage from "../pages/LoginPage.vue";
import RegisterPage from "../pages/RegisterPage.vue";
import ResetPasswordPage from "../pages/ResetPasswordPage.vue";
import ReputationPage from "../pages/ReputationPage.vue";
import SecurityPage from "../pages/SecurityPage.vue";
import SubmissionsPage from "../pages/SubmissionsPage.vue";
import TrustCasesPage from "../pages/TrustCasesPage.vue";
import ThirdPartyAuthorizePage from "../pages/ThirdPartyAuthorizePage.vue";
import AuthorizedApplicationsPage from "../pages/AuthorizedApplicationsPage.vue";
import UserCenterPage from "../pages/UserCenterPage.vue";
import VerifyEmailPage from "../pages/VerifyEmailPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage },
    { path: "/hash/:algorithm/:digest", component: HashDetailPage },
    { path: "/login", component: LoginPage, meta: { guestOnly: true } },
    { path: "/register", component: RegisterPage, meta: { guestOnly: true } },
    { path: "/forgot-password", component: ForgotPasswordPage, meta: { guestOnly: true } },
    { path: "/reset-password", component: ResetPasswordPage },
    { path: "/verify-email", component: VerifyEmailPage },
    { path: "/security", component: SecurityPage, meta: { requiresAuth: true } },
    { path: "/user-center", component: UserCenterPage, meta: { requiresAuth: true } },
    { path: "/community", component: CommunityHomePage },
    { path: "/community/search", component: CommunitySearchPage },
    { path: "/community/activity", component: CommunityActivityPage },
    { path: "/community/new", component: CommunityPostComposerPage, meta: { requiresAuth: true } },
    { path: "/community/groups", component: CommunityGroupsPage },
    { path: "/community/groups/:slug", component: CommunityGroupPage },
    {
      path: "/community/bookmarks",
      component: CommunityBookmarksPage,
      meta: { requiresAuth: true },
    },
    {
      path: "/community/notifications",
      component: CommunityNotificationsPage,
      meta: { requiresAuth: true },
    },
    { path: "/community/posts/:postId", component: CommunityPostPage },
    {
      path: "/community/users/:username/followers",
      component: CommunityRelationsPage,
      meta: { direction: "followers" },
    },
    {
      path: "/community/users/:username/following",
      component: CommunityRelationsPage,
      meta: { direction: "following" },
    },
    { path: "/community/users/:username", component: CommunityProfilePage },
    {
      path: "/community/settings",
      component: CommunitySettingsPage,
      meta: { requiresAuth: true },
    },
    { path: "/community/legacy", component: CommunityPage },
    { path: "/account/profile", redirect: "/user-center" },
    { path: "/account/activity", component: AccountActivityPage, meta: { requiresAuth: true } },
    { path: "/account/privacy", component: AccountPrivacyPage, meta: { requiresAuth: true } },
    { path: "/submissions", component: SubmissionsPage, meta: { requiresAuth: true } },
    { path: "/reputation", component: ReputationPage, meta: { requiresAuth: true } },
    { path: "/trust-cases", component: TrustCasesPage, meta: { requiresAuth: true } },
    { path: "/oauth/authorize", component: ThirdPartyAuthorizePage, meta: { requiresAuth: true } },
    { path: "/account/authorized-applications", component: AuthorizedApplicationsPage, meta: { requiresAuth: true } },
  ],
});

router.beforeEach((to) => {
  const authenticated = Boolean(sessionStorage.getItem("password_detective_session_v2"));
  if (to.meta.requiresAuth && !authenticated) return "/login";
  if (to.meta.guestOnly && authenticated) return "/";
  return true;
});

export default router;
