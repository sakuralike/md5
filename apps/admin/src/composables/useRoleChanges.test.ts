import {
  ApiError,
  type RoleChangeMutationResponse,
  type RoleChangeRequest,
  type RoleChangeRequestListResponse,
} from "@password-detective/api-contract";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRoleChanges, type RoleChangesDependencies } from "./useRoleChanges";

const pendingRequest: RoleChangeRequest = {
  id: "request-pending-001",
  target_user_id: "synthetic-user-001",
  expected_role: "user",
  requested_role: "trusted_contributor",
  status: "pending",
  requested_by: "synthetic-admin-requester",
  reviewed_by: null,
  reason_code: "trust_promotion",
  review_reason_code: null,
  created_at: "2026-08-08T08:00:00Z",
  reviewed_at: null,
};

function mutationResponse(
  request: RoleChangeRequest,
  revokedSessionCount = 0,
): RoleChangeMutationResponse {
  return {
    request,
    revoked_session_count: revokedSessionCount,
    audit_id: "synthetic-audit-001",
    request_id: "synthetic-request-id",
  };
}

function listResponse(
  items: RoleChangeRequest[],
  options: Partial<Pick<RoleChangeRequestListResponse, "page" | "page_size" | "total">> = {},
): RoleChangeRequestListResponse {
  return {
    items,
    page: options.page ?? 1,
    page_size: options.page_size ?? 20,
    total: options.total ?? items.length,
  };
}

function createDependencies(): RoleChangesDependencies {
  return {
    accessToken: () => "synthetic-admin-token",
    randomUUID: vi.fn(() => "synthetic-idempotency-key"),
    listRoleChangeRequests: vi.fn().mockResolvedValue(listResponse([pendingRequest])),
    createRoleChangeRequest: vi.fn().mockResolvedValue(mutationResponse(pendingRequest)),
    approveRoleChangeRequest: vi.fn(),
    rejectRoleChangeRequest: vi.fn(),
    reauthenticateAdmin: vi.fn().mockResolvedValue({ reauth_token: "synthetic-reauth-token" }),
  };
}

describe("useRoleChanges", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads filtered pages, exposes range information, and clears sensitive fields when paging", async () => {
    const dependencies = createDependencies();
    const secondPageRequest = { ...pendingRequest, id: "request-pending-021" };
    vi.mocked(dependencies.listRoleChangeRequests)
      .mockResolvedValueOnce(listResponse([pendingRequest], { page: 1, total: 21 }))
      .mockResolvedValueOnce(listResponse([secondPageRequest], { page: 2, total: 21 }));
    const state = useRoleChanges(dependencies);

    await state.loadRequests();
    expect(dependencies.listRoleChangeRequests).toHaveBeenNthCalledWith(
      1,
      { status: "pending", page: 1, pageSize: 20 },
      "synthetic-admin-token",
    );
    expect(state.totalPages.value).toBe(2);
    expect(state.rangeLabel.value).toBe("第 1–20 条，共 21 条");

    state.selectRequest(pendingRequest);
    state.currentPassword.value = "synthetic-password";
    state.totpCode.value = "123456";
    await state.changePage(2);

    expect(dependencies.listRoleChangeRequests).toHaveBeenNthCalledWith(
      2,
      { status: "pending", page: 2, pageSize: 20 },
      "synthetic-admin-token",
    );
    expect(state.items.value).toEqual([secondPageRequest]);
    expect(state.selected.value).toBeNull();
    expect(state.currentPassword.value).toBe("");
    expect(state.totpCode.value).toBe("");
    expect(state.rangeLabel.value).toBe("第 21–21 条，共 21 条");
  });

  it("creates a request with one-time reauthentication and keeps success visible after refresh", async () => {
    const dependencies = createDependencies();
    const state = useRoleChanges(dependencies);
    state.createUserId.value = "  synthetic-user-001  ";
    state.currentPassword.value = "synthetic-password";
    state.totpCode.value = "123456";

    await state.createRequest();

    expect(dependencies.reauthenticateAdmin).toHaveBeenCalledWith(
      { currentPassword: "synthetic-password", totpCode: "123456" },
      "synthetic-admin-token",
    );
    expect(dependencies.createRoleChangeRequest).toHaveBeenCalledWith(
      "synthetic-user-001",
      {
        expectedRole: "user",
        requestedRole: "trusted_contributor",
        reasonCode: "trust_promotion",
        reauthToken: "synthetic-reauth-token",
      },
      "synthetic-admin-token",
      "synthetic-idempotency-key",
    );
    expect(state.success.value).toContain("已创建");
    expect(state.error.value).toBe("");
    expect(state.selected.value).toEqual(pendingRequest);
    expect(state.createUserId.value).toBe("");
    expect(state.currentPassword.value).toBe("");
    expect(state.totpCode.value).toBe("");
  });

  it("approves a pending request, reports revoked sessions, and preserves the reviewed detail", async () => {
    const dependencies = createDependencies();
    const approvedRequest: RoleChangeRequest = {
      ...pendingRequest,
      status: "approved",
      reviewed_by: "synthetic-admin-reviewer",
      review_reason_code: "verified",
      reviewed_at: "2026-08-08T09:00:00Z",
    };
    vi.mocked(dependencies.approveRoleChangeRequest).mockResolvedValue(
      mutationResponse(approvedRequest, 3),
    );
    vi.mocked(dependencies.listRoleChangeRequests).mockResolvedValue(listResponse([]));
    const state = useRoleChanges(dependencies);
    state.selectRequest(pendingRequest);
    state.currentPassword.value = "synthetic-password";
    state.totpCode.value = "123456";

    await state.review("approve");

    expect(dependencies.approveRoleChangeRequest).toHaveBeenCalledWith(
      pendingRequest.id,
      {
        expectedStatus: "pending",
        reasonCode: "verified",
        reauthToken: "synthetic-reauth-token",
      },
      "synthetic-admin-token",
      "synthetic-idempotency-key",
    );
    expect(state.success.value).toContain("已撤销 3 个目标活跃会话");
    expect(state.selected.value).toEqual(approvedRequest);
    expect(state.pendingSelected.value).toBe(false);
    expect(state.currentPassword.value).toBe("");
    expect(state.totpCode.value).toBe("");
  });

  it("rejects a pending request with the selected review reason", async () => {
    const dependencies = createDependencies();
    const rejectedRequest: RoleChangeRequest = {
      ...pendingRequest,
      status: "rejected",
      reviewed_by: "synthetic-admin-reviewer",
      review_reason_code: "policy_conflict",
      reviewed_at: "2026-08-08T09:05:00Z",
    };
    vi.mocked(dependencies.rejectRoleChangeRequest).mockResolvedValue(
      mutationResponse(rejectedRequest),
    );
    const state = useRoleChanges(dependencies);
    state.selectRequest(pendingRequest);
    state.reviewReason.value = "policy_conflict";
    state.currentPassword.value = "synthetic-password";
    state.totpCode.value = "123456";

    await state.review("reject");

    expect(dependencies.rejectRoleChangeRequest).toHaveBeenCalledWith(
      pendingRequest.id,
      expect.objectContaining({ reasonCode: "policy_conflict", expectedStatus: "pending" }),
      "synthetic-admin-token",
      "synthetic-idempotency-key",
    );
    expect(state.success.value).toContain("已拒绝");
    expect(state.selected.value).toEqual(rejectedRequest);
  });

  it("renders service errors and always clears credentials after a failed review", async () => {
    const dependencies = createDependencies();
    vi.mocked(dependencies.reauthenticateAdmin).mockRejectedValue(
      new ApiError(409, {
        code: "admin.role_change_review_conflict",
        message: "角色变更请求状态已变化",
        request_id: "synthetic-request-id",
        details: {},
      }),
    );
    const state = useRoleChanges(dependencies);
    state.selectRequest(pendingRequest);
    state.currentPassword.value = "synthetic-password";
    state.totpCode.value = "123456";

    await state.review("approve");

    expect(state.error.value).toBe("角色变更请求状态已变化");
    expect(state.currentPassword.value).toBe("");
    expect(state.totpCode.value).toBe("");
    expect(dependencies.approveRoleChangeRequest).not.toHaveBeenCalled();
  });

  it("rejects invalid create input before requesting a reauthentication grant", async () => {
    const dependencies = createDependencies();
    const state = useRoleChanges(dependencies);
    state.createUserId.value = "synthetic-user-001";
    state.createRequestedRole.value = "user";
    state.currentPassword.value = "synthetic-password";
    state.totpCode.value = "123456";

    await state.createRequest();

    expect(state.error.value).toBe("当前角色与申请角色不能相同");
    expect(state.currentPassword.value).toBe("");
    expect(state.totpCode.value).toBe("");
    expect(dependencies.reauthenticateAdmin).not.toHaveBeenCalled();
    expect(dependencies.createRoleChangeRequest).not.toHaveBeenCalled();
  });
});
