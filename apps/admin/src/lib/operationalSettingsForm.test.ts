import type { OperationalSettingsSnapshot } from "@password-detective/api-contract";
import { ref } from "vue";
import { describe, expect, it } from "vitest";
import { cloneOperationalSettingsSnapshot } from "./operationalSettingsForm";

const snapshot: OperationalSettingsSnapshot = {
  site_name: "合成站点",
  site_logo_url: "",
  site_navigation: [
    { label: "首页", path: "/", enabled: true, requires_auth: false },
  ],
  icp_record: "",
  public_security_record: "",
  copyright_text: "",
  public_contact_email: "",
  maintenance_enabled: false,
  maintenance_message: "系统正在维护，请稍后再试。",
  maintenance_allowed_ip_cidrs: [],
  max_active_sessions: 0,
  session_overflow_policy: "deny_new",
  referral_reward_points: 10,
  daily_reveal_quota: 20,
  reauthentication_ttl_minutes: 5,
  privacy_deletion_grace_hours: 72,
  desktop_min_client_version: "1.0.0",
  desktop_update_download_cache_seconds: 3600,
  user_levels: [
    {
      code: "synthetic",
      name: "合成等级",
      description: "仅用于测试",
      min_growth_points: 0,
      daily_reveal_quota: 20,
      can_submit: true,
    },
  ],
};

describe("cloneOperationalSettingsSnapshot", () => {
  it("clones a Vue ref value without retaining reactive nested state", () => {
    const reactiveSnapshot = ref(snapshot);

    const cloned = cloneOperationalSettingsSnapshot(reactiveSnapshot.value);
    cloned.site_navigation[0].label = "已修改";
    cloned.user_levels[0].name = "已修改等级";

    expect(cloned).not.toBe(reactiveSnapshot.value);
    expect(reactiveSnapshot.value.site_navigation[0].label).toBe("首页");
    expect(reactiveSnapshot.value.user_levels[0].name).toBe("合成等级");
  });
});
