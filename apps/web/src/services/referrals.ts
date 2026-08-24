import type { ReferralProfileResponse } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getMyReferralProfile(token: string): Promise<ReferralProfileResponse> {
  return apiRequest<ReferralProfileResponse>("/referrals/me", {}, token);
}
