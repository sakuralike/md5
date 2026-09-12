import { defineConfig, devices } from "@playwright/test";

const apiPort = 18100;
const webPort = 15173;
const adminPort = 15174;
const e2eApiBaseUrl = process.env.E2E_DIRECT_API !== "0"
  ? `http://127.0.0.1:${apiPort}/api/v1`
  : "/api/v1";

process.env.E2E_ADMIN_USERNAME ??= "synthetic_e2e_admin";
process.env.E2E_ADMIN_EMAIL ??= "synthetic-e2e-admin@example.com";
process.env.E2E_ADMIN_PASSWORD ??= "Synthetic-E2E-Admin-2026";
process.env.E2E_ADMIN_WORKFLOW_ID ??= "10000000-0000-4000-8000-000000000001";
process.env.E2E_ADMIN_WORKFLOW_USERNAME ??= "synthetic_e2e_workflow_admin";
process.env.E2E_ADMIN_WORKFLOW_EMAIL ??= "synthetic-e2e-workflow-admin@example.com";
process.env.E2E_ADMIN_WORKFLOW_PASSWORD ??= "Synthetic-E2E-Workflow-Admin-2026";
process.env.E2E_ADMIN_WORKFLOW_TOTP_SECRET ??= "JBSWY3DPEHPK3PXP";
process.env.E2E_ADMIN_REVIEWER_ID ??= "10000000-0000-4000-8000-000000000002";
process.env.E2E_ADMIN_REVIEWER_USERNAME ??= "synthetic_e2e_reviewer_admin";
process.env.E2E_ADMIN_REVIEWER_EMAIL ??= "synthetic-e2e-reviewer-admin@example.com";
process.env.E2E_ADMIN_REVIEWER_PASSWORD ??= "Synthetic-E2E-Reviewer-Admin-2026";
process.env.E2E_ADMIN_REVIEWER_TOTP_SECRET ??= "KRSXG5DSNFXGOIDB";
process.env.E2E_ADMIN_GOVERNANCE_USER_ID ??= "10000000-0000-4000-8000-000000000003";
process.env.E2E_ADMIN_GOVERNANCE_USERNAME ??= "synthetic_e2e_governance_user";
process.env.E2E_ADMIN_GOVERNANCE_EMAIL ??= "synthetic-e2e-governance-user@example.com";
process.env.E2E_ADMIN_GOVERNANCE_PASSWORD ??= "Synthetic-E2E-Governance-User-2026";
process.env.E2E_ADMIN_GOVERNANCE_SESSION_ID ??= "40000000-0000-4000-8000-000000000003";
process.env.E2E_ADMIN_ROLE_TARGET_ID ??= "10000000-0000-4000-8000-000000000004";
process.env.E2E_ADMIN_ROLE_TARGET_USERNAME ??= "synthetic_e2e_role_target";
process.env.E2E_ADMIN_ROLE_TARGET_EMAIL ??= "synthetic-e2e-role-target@example.com";
process.env.E2E_ADMIN_ROLE_TARGET_PASSWORD ??= "Synthetic-E2E-Role-Target-2026";
process.env.E2E_ADMIN_ROLE_TARGET_SESSION_ID ??= "40000000-0000-4000-8000-000000000004";
process.env.E2E_WEB_USERNAME ??= "synthetic_e2e_journey";
process.env.E2E_WEB_EMAIL ??= "synthetic-e2e-journey@example.com";
process.env.E2E_WEB_PASSWORD ??= "Synthetic-E2E-Web-2026";
process.env.E2E_WEB_SECURITY_USERNAME ??= "synthetic_e2e_security";
process.env.E2E_WEB_SECURITY_EMAIL ??= "synthetic-e2e-security@example.com";
process.env.E2E_WEB_SECURITY_PASSWORD ??= "Synthetic-E2E-Security-2026";
process.env.E2E_WEB_SECURITY_NEW_PASSWORD ??= "Synthetic-E2E-Security-Next-2026";
process.env.E2E_WEB_SECURITY_SESSION_ID ??= "40000000-0000-4000-8000-000000000001";
process.env.E2E_WEB_SECURITY_SECOND_SESSION_ID ??= "40000000-0000-4000-8000-000000000002";
process.env.E2E_WEB_TOTP_USERNAME ??= "synthetic_e2e_totp";
process.env.E2E_WEB_TOTP_EMAIL ??= "synthetic-e2e-totp@example.com";
process.env.E2E_WEB_TOTP_PASSWORD ??= "Synthetic-E2E-Totp-2026";
process.env.E2E_WEB_PRIVACY_USERNAME ??= "synthetic_e2e_privacy";
process.env.E2E_WEB_PRIVACY_EMAIL ??= "synthetic-e2e-privacy@example.com";
process.env.E2E_WEB_PRIVACY_PASSWORD ??= "Synthetic-E2E-Privacy-2026";
process.env.E2E_WEB_DM_SENDER_USERNAME ??= "synthetic_e2e_dm_sender";
process.env.E2E_WEB_DM_SENDER_EMAIL ??= "synthetic-e2e-dm-sender@example.com";
process.env.E2E_WEB_DM_SENDER_PASSWORD ??= "Synthetic-E2E-Dm-Sender-2026";
process.env.E2E_WEB_DM_RECIPIENT_USERNAME ??= "synthetic_e2e_dm_recipient";
process.env.E2E_WEB_DM_RECIPIENT_EMAIL ??= "synthetic-e2e-dm-recipient@example.com";
process.env.E2E_WEB_DM_RECIPIENT_PASSWORD ??= "Synthetic-E2E-Dm-Recipient-2026";
process.env.E2E_WEB_DM_OUTSIDER_USERNAME ??= "synthetic_e2e_dm_outsider";
process.env.E2E_WEB_DM_OUTSIDER_EMAIL ??= "synthetic-e2e-dm-outsider@example.com";
process.env.E2E_WEB_DM_OUTSIDER_PASSWORD ??= "Synthetic-E2E-Dm-Outsider-2026";
process.env.E2E_WEB_EMAIL_VERIFY_USER_ID ??= "10000000-0000-4000-8000-000000000005";
process.env.E2E_WEB_EMAIL_VERIFY_USERNAME ??= "synthetic_e2e_email_verify";
process.env.E2E_WEB_EMAIL_VERIFY_EMAIL ??= "synthetic-e2e-email-verify@example.com";
process.env.E2E_WEB_EMAIL_VERIFY_PASSWORD ??= "Synthetic-E2E-Email-Verify-2026";
process.env.E2E_WEB_EMAIL_VERIFY_TOKEN_ID ??= "70000000-0000-4000-8000-000000000001";
process.env.E2E_WEB_EMAIL_VERIFY_TOKEN ??= "synthetic-email-verification-token-2026";
process.env.E2E_WEB_EMAIL_VERIFY_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000005";
process.env.E2E_WEB_EMAIL_VERIFY_REFRESH_TOKEN ??= "synthetic-email-refresh-token-2026";
process.env.E2E_WEB_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000006";
process.env.E2E_WEB_REFRESH_TOKEN ??= "synthetic-web-refresh-token-2026";
process.env.E2E_WEB_EXPIRED_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000007";
process.env.E2E_WEB_EXPIRED_REFRESH_TOKEN ??= "synthetic-web-expired-refresh-token-2026";
process.env.E2E_WEB_CONCURRENT_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000008";
process.env.E2E_WEB_CONCURRENT_REFRESH_TOKEN ??= "synthetic-web-concurrent-refresh-token-2026";
process.env.E2E_WEB_ACCESSIBILITY_SECURITY_USERNAME ??= "synthetic_e2e_accessibility_security";
process.env.E2E_WEB_ACCESSIBILITY_SECURITY_EMAIL ??= "synthetic-e2e-accessibility-security@example.com";
process.env.E2E_WEB_ACCESSIBILITY_SECURITY_PASSWORD ??= "Synthetic-E2E-Accessibility-Security-2026";
process.env.E2E_WEB_ACCESSIBILITY_SECURITY_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000009";
process.env.E2E_WEB_ACCESSIBILITY_SECURITY_REFRESH_TOKEN ??= "synthetic-web-accessibility-security-refresh-token-2026";
process.env.E2E_WEB_ACCESSIBILITY_PRIVACY_USERNAME ??= "synthetic_e2e_accessibility_privacy";
process.env.E2E_WEB_ACCESSIBILITY_PRIVACY_EMAIL ??= "synthetic-e2e-accessibility-privacy@example.com";
process.env.E2E_WEB_ACCESSIBILITY_PRIVACY_PASSWORD ??= "Synthetic-E2E-Accessibility-Privacy-2026";
process.env.E2E_WEB_ACCESSIBILITY_PRIVACY_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000010";
process.env.E2E_WEB_ACCESSIBILITY_PRIVACY_REFRESH_TOKEN ??= "synthetic-web-accessibility-privacy-refresh-token-2026";
process.env.E2E_ADMIN_ACCESSIBILITY_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000011";
process.env.E2E_ADMIN_ACCESSIBILITY_REFRESH_TOKEN ??= "synthetic-admin-accessibility-refresh-token-2026";
process.env.E2E_WEB_ACCESSIBILITY_WORKFLOW_USERNAME ??= "synthetic_e2e_accessibility_workflow";
process.env.E2E_WEB_ACCESSIBILITY_WORKFLOW_EMAIL ??= "synthetic-e2e-accessibility-workflow@example.com";
process.env.E2E_WEB_ACCESSIBILITY_WORKFLOW_PASSWORD ??= "Synthetic-E2E-Accessibility-Workflow-2026";
process.env.E2E_WEB_ACCESSIBILITY_WORKFLOW_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000012";
process.env.E2E_WEB_ACCESSIBILITY_WORKFLOW_REFRESH_TOKEN ??= "synthetic-web-accessibility-workflow-refresh-token-2026";
process.env.E2E_ADMIN_ACCESSIBILITY_OPERATIONS_REFRESH_FAMILY_ID ??= "40000000-0000-4000-8000-000000000013";
process.env.E2E_ADMIN_ACCESSIBILITY_OPERATIONS_REFRESH_TOKEN ??= "synthetic-admin-accessibility-operations-refresh-token-2026";
process.env.E2E_VERIFIED_SHA256 ??= "c".repeat(64);
process.env.E2E_VERIFIED_MD5 ??= "d".repeat(32);
process.env.E2E_VERIFIED_PASSWORD ??= "Synthetic-Verified-Password-2026!";
process.env.E2E_VERIFIED_CANDIDATE_ID ??= "20000000-0000-4000-8000-000000000000";
process.env.E2E_UNMATCHED_SHA256 ??= "e".repeat(64);
process.env.E2E_ADMIN_PENDING_CANDIDATE_ID ??= "20000000-0000-4000-8000-000000000001";
process.env.E2E_ADMIN_PENDING_SHA256 ??= "f".repeat(64);
process.env.E2E_ADMIN_CASE_CANDIDATE_ID ??= "20000000-0000-4000-8000-000000000002";
process.env.E2E_ADMIN_CASE_SHA256 ??= "b".repeat(64);
process.env.E2E_ADMIN_CASE_ID ??= "30000000-0000-4000-8000-000000000001";
process.env.E2E_ADMIN_RISK_CANDIDATE_ID ??= "20000000-0000-4000-8000-000000000003";
process.env.E2E_ADMIN_RISK_SHA256 ??= "a".repeat(64);
process.env.E2E_ADMIN_RISK_FEEDBACK_ID ??= "50000000-0000-4000-8000-000000000001";
process.env.E2E_ADMIN_RISK_EVIDENCE_ID ??= "50000000-0000-4000-8000-000000000002";
process.env.E2E_ADMIN_RISK_ALERT_ID ??= "60000000-0000-4000-8000-000000000001";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: ".local/playwright/results",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [
    ["list"],
    ["html", { outputFolder: ".local/playwright/report", open: "never" }],
  ],
  expect: {
    timeout: 10_000,
  },
  use: {
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off",
  },
  projects: [
    ...[
      { name: "chromium", device: devices["Desktop Chrome"] },
      { name: "firefox", device: devices["Desktop Firefox"] },
      { name: "webkit", device: devices["Desktop Safari"] },
    ].flatMap(({ name, device }) => [
      {
        name: `web-${name}`,
        testMatch: /(^|[\\/])web-[^\\/]+\.spec\.ts$/,
        use: {
          ...device,
          baseURL: `http://127.0.0.1:${webPort}`,
        },
      },
      {
        name: `admin-${name}`,
        testMatch: /(^|[\\/])admin-[^\\/]+\.spec\.ts$/,
        use: {
          ...device,
          baseURL: `http://127.0.0.1:${adminPort}`,
        },
      },
    ]),
  ],
  webServer: [
    {
      command: "node scripts/e2e/start-api.mjs",
      url: `http://127.0.0.1:${apiPort}/api/v1/health/ready`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        E2E_API_PORT: String(apiPort),
        E2E_WEB_ORIGIN: `http://127.0.0.1:${webPort}`,
        E2E_ADMIN_ORIGIN: `http://127.0.0.1:${adminPort}`,
      },
    },
    {
      command: `pnpm --dir apps/web exec vite --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: `http://127.0.0.1:${webPort}`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_BASE_URL: e2eApiBaseUrl,
        VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
      },
    },
    {
      command: `pnpm --dir apps/admin exec vite --host 127.0.0.1 --port ${adminPort} --strictPort`,
      url: `http://127.0.0.1:${adminPort}/login`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_BASE_URL: e2eApiBaseUrl,
        VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
      },
    },
  ],
});
