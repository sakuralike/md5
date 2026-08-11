import type {
  GrowthEventsResponse,
  MyFeedbackHistoryResponse,
  PointsLedgerResponse,
  ReputationEventsResponse,
  TrustProfileResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface TrustCenterData {
  profile: TrustProfileResponse;
  points: PointsLedgerResponse;
  reputation: ReputationEventsResponse;
  feedback: MyFeedbackHistoryResponse;
  growth: GrowthEventsResponse;
}

export async function loadTrustCenter(token: string): Promise<TrustCenterData> {
  const [profile, points, reputation, feedback, growth] = await Promise.all([
    apiRequest<TrustProfileResponse>("/me/trust-profile", {}, token),
    apiRequest<PointsLedgerResponse>("/me/points?page=1&page_size=50", {}, token),
    apiRequest<ReputationEventsResponse>("/me/reputation?page=1&page_size=50", {}, token),
    apiRequest<MyFeedbackHistoryResponse>("/me/feedback?page=1&page_size=50", {}, token),
    apiRequest<GrowthEventsResponse>("/me/growth-events?page=1&page_size=50", {}, token),
  ]);
  return { profile, points, reputation, feedback, growth };
}
