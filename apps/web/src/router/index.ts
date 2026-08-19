import { createRouter, createWebHistory } from "vue-router";
import type { SeoContentKind, SeoRouteScope } from "../lib/seo";
import AccountActivityPage from "../pages/AccountActivityPage.vue";
import AccountPrivacyPage from "../pages/AccountPrivacyPage.vue";
import CommunityPage from "../pages/CommunityPage.vue";
import CommunityActivityPage from "../pages/CommunityActivityPage.vue";
import CommunityBookmarksPage from "../pages/CommunityBookmarksPage.vue";
import CommunityHomePage from "../pages/CommunityHomePage.vue";
import CommunityMessagesPage from "../pages/CommunityMessagesPage.vue";
import CommunityConversationPage from "../pages/CommunityConversationPage.vue";
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
import RewardsPage from "../pages/RewardsPage.vue";
import SecurityPage from "../pages/SecurityPage.vue";
import SecurityToolsPage from "../pages/SecurityToolsPage.vue";
import StatisticsPage from "../pages/StatisticsPage.vue";
import SubmissionsPage from "../pages/SubmissionsPage.vue";
import TrustCasesPage from "../pages/TrustCasesPage.vue";
import ThirdPartyAuthorizePage from "../pages/ThirdPartyAuthorizePage.vue";
import AuthorizedApplicationsPage from "../pages/AuthorizedApplicationsPage.vue";
import UserCenterPage from "../pages/UserCenterPage.vue";
import DeveloperApplicationsPage from "../pages/DeveloperApplicationsPage.vue";
import VerifyEmailPage from "../pages/VerifyEmailPage.vue";

declare module "vue-router" {
  interface RouteMeta {
    seoScope?: SeoRouteScope;
    seoTitle?: string;
    seoContent?: SeoContentKind;
  }
}

const publicSeo = { seoScope: "public" as const };
const guestSeo = { seoScope: "guest" as const };
const privateSeo = { seoScope: "private" as const };

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage, meta: publicSeo },
    { path: "/hash/:algorithm/:digest", component: HashDetailPage, meta: privateSeo },
    { path: "/login", component: LoginPage, meta: { ...guestSeo, guestOnly: true } },
    { path: "/register", component: RegisterPage, meta: { ...guestSeo, guestOnly: true } },
    { path: "/forgot-password", component: ForgotPasswordPage, meta: { ...guestSeo, guestOnly: true } },
    { path: "/reset-password", component: ResetPasswordPage, meta: guestSeo },
    { path: "/verify-email", component: VerifyEmailPage, meta: guestSeo },
    { path: "/security", component: SecurityPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/tools", component: SecurityToolsPage, meta: { ...publicSeo, seoTitle: "本地安全工具" } },
    { path: "/statistics", component: StatisticsPage, meta: { ...publicSeo, seoTitle: "算法分布" } },
    { path: "/user-center", component: UserCenterPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/developer", redirect: "/developer/applications", meta: privateSeo },
    { path: "/developer/apply", component: DeveloperApplicationsPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/developer/applications", component: DeveloperApplicationsPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/community", component: CommunityHomePage, meta: { ...publicSeo, seoTitle: "社区" } },
    { path: "/community/search", component: CommunitySearchPage, meta: privateSeo },
    { path: "/community/activity", component: CommunityActivityPage, meta: privateSeo },
    { path: "/community/new", component: CommunityPostComposerPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/community/groups", component: CommunityGroupsPage, meta: privateSeo },
    { path: "/community/groups/:slug", component: CommunityGroupPage, meta: { ...privateSeo, seoContent: "group" } },
    {
      path: "/community/bookmarks",
      component: CommunityBookmarksPage,
      meta: { ...privateSeo, requiresAuth: true },
    },
    {
      path: "/community/notifications",
      component: CommunityNotificationsPage,
      meta: { ...privateSeo, requiresAuth: true },
    },
    {
      path: "/community/messages",
      component: CommunityMessagesPage,
      meta: { ...privateSeo, requiresAuth: true },
    },
    {
      path: "/community/messages/:conversationId",
      component: CommunityConversationPage,
      meta: { ...privateSeo, requiresAuth: true },
    },
    { path: "/community/posts/:postId", component: CommunityPostPage, meta: { ...privateSeo, seoContent: "post" } },
    {
      path: "/community/users/:username/followers",
      component: CommunityRelationsPage,
      meta: { ...privateSeo, direction: "followers" },
    },
    {
      path: "/community/users/:username/following",
      component: CommunityRelationsPage,
      meta: { ...privateSeo, direction: "following" },
    },
    { path: "/community/users/:username", component: CommunityProfilePage, meta: privateSeo },
    {
      path: "/community/settings",
      component: CommunitySettingsPage,
      meta: { ...privateSeo, requiresAuth: true },
    },
    { path: "/community/legacy", component: CommunityPage, meta: privateSeo },
    { path: "/account/profile", redirect: "/user-center", meta: privateSeo },
    { path: "/account/activity", component: AccountActivityPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/account/privacy", component: AccountPrivacyPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/submissions", component: SubmissionsPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/reputation", component: ReputationPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/rewards", component: RewardsPage, meta: { ...publicSeo, seoTitle: "积分商城" } },
    { path: "/trust-cases", component: TrustCasesPage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/oauth/authorize", component: ThirdPartyAuthorizePage, meta: { ...privateSeo, requiresAuth: true } },
    { path: "/account/authorized-applications", component: AuthorizedApplicationsPage, meta: { ...privateSeo, requiresAuth: true } },
  ],
});

router.beforeEach((to) => {
  const authenticated = Boolean(sessionStorage.getItem("password_detective_session_v2"));
  if (to.meta.requiresAuth && !authenticated) return "/login";
  if (to.meta.guestOnly && authenticated) return "/";
  return true;
});

export default router;
