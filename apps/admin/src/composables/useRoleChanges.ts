import {
  ApiError,
  type RoleChangeReasonCode,
  type RoleChangeRequest,
  type RoleChangeRequestStatus,
  type RoleChangeReviewReasonCode,
  type UserRole,
} from "@password-detective/api-contract";
import { computed, ref } from "vue";
import type {
  RoleChangeCreateInput,
  RoleChangeFilters,
  RoleChangeReviewInput,
} from "../services/roleChanges";
import type {
  RoleChangeMutationResponse,
  RoleChangeRequestListResponse,
} from "@password-detective/api-contract";

export type RoleChangeStatusFilter = "all" | RoleChangeRequestStatus;
export type RoleChangeReviewAction = "approve" | "reject";

type ListRoleChangeRequests = (
  filters: RoleChangeFilters,
  token: string,
) => Promise<RoleChangeRequestListResponse>;
type CreateRoleChangeRequest = (
  userId: string,
  input: RoleChangeCreateInput,
  token: string,
  idempotencyKey: string,
) => Promise<RoleChangeMutationResponse>;
type ReviewRoleChangeRequest = (
  requestId: string,
  input: RoleChangeReviewInput,
  token: string,
  idempotencyKey: string,
) => Promise<RoleChangeMutationResponse>;
type ReauthenticateAdmin = (
  input: { currentPassword: string; totpCode: string },
  token: string,
) => Promise<{ reauth_token: string }>;

export interface RoleChangesDependencies {
  accessToken: () => string;
  randomUUID: () => string;
  listRoleChangeRequests: ListRoleChangeRequests;
  createRoleChangeRequest: CreateRoleChangeRequest;
  approveRoleChangeRequest: ReviewRoleChangeRequest;
  rejectRoleChangeRequest: ReviewRoleChangeRequest;
  reauthenticateAdmin: ReauthenticateAdmin;
}

interface LoadOptions {
  preserveMessages?: boolean;
  preserveSelection?: boolean;
}

const DEFAULT_PAGE_SIZE = 20;

export function useRoleChanges(dependencies: RoleChangesDependencies) {
  const items = ref<RoleChangeRequest[]>([]);
  const selected = ref<RoleChangeRequest | null>(null);
  const filterStatus = ref<RoleChangeStatusFilter>("pending");
  const page = ref(1);
  const pageSize = ref(DEFAULT_PAGE_SIZE);
  const total = ref(0);
  const loading = ref(false);
  const busy = ref(false);
  const error = ref("");
  const success = ref("");
  const currentPassword = ref("");
  const totpCode = ref("");
  const reviewReason = ref<RoleChangeReviewReasonCode>("verified");
  const createUserId = ref("");
  const createExpectedRole = ref<UserRole>("user");
  const createRequestedRole = ref<UserRole>("trusted_contributor");
  const createReason = ref<RoleChangeReasonCode>("trust_promotion");
  let loadSequence = 0;

  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
  const rangeLabel = computed(() => {
    if (total.value === 0) return "暂无请求";
    const start = (page.value - 1) * pageSize.value + 1;
    const end = Math.min(page.value * pageSize.value, total.value);
    return `第 ${start}–${end} 条，共 ${total.value} 条`;
  });
  const pendingSelected = computed(() => selected.value?.status === "pending");

  function describeError(value: unknown): string {
    if (value instanceof ApiError) return value.body.message;
    return value instanceof Error ? value.message : "角色治理服务暂时不可用";
  }

  function clearMessages(): void {
    error.value = "";
    success.value = "";
  }

  function clearCredentials(): void {
    currentPassword.value = "";
    totpCode.value = "";
  }

  function selectRequest(item: RoleChangeRequest): void {
    selected.value = item;
    clearMessages();
    clearCredentials();
  }

  async function loadRequests(options: LoadOptions = {}): Promise<void> {
    const sequence = ++loadSequence;
    loading.value = true;
    if (!options.preserveMessages) clearMessages();
    try {
      const response = await dependencies.listRoleChangeRequests(
        {
          status: filterStatus.value === "all" ? undefined : filterStatus.value,
          page: page.value,
          pageSize: pageSize.value,
        },
        dependencies.accessToken(),
      );
      if (sequence !== loadSequence) return;
      total.value = response.total;
      pageSize.value = response.page_size;
      const responseTotalPages = Math.max(1, Math.ceil(response.total / response.page_size));
      if (page.value > responseTotalPages) {
        page.value = responseTotalPages;
        await loadRequests(options);
        return;
      }
      page.value = response.page;
      items.value = response.items;
      if (selected.value && !options.preserveSelection) {
        selected.value = response.items.find((item) => item.id === selected.value?.id) ?? null;
      }
    } catch (value) {
      if (sequence !== loadSequence) return;
      error.value = describeError(value);
      if (!options.preserveSelection) selected.value = null;
    } finally {
      if (sequence === loadSequence) loading.value = false;
    }
  }

  async function changeFilter(): Promise<void> {
    page.value = 1;
    selected.value = null;
    clearCredentials();
    await loadRequests();
  }

  async function changePage(nextPage: number): Promise<void> {
    page.value = Math.min(Math.max(1, nextPage), totalPages.value);
    selected.value = null;
    clearCredentials();
    await loadRequests();
  }

  async function grant(): Promise<string> {
    if (!currentPassword.value || !/^\d{6}$/.test(totpCode.value)) {
      throw new Error("角色治理需要当前密码和 6 位数字 TOTP 动态码");
    }
    const response = await dependencies.reauthenticateAdmin(
      { currentPassword: currentPassword.value, totpCode: totpCode.value },
      dependencies.accessToken(),
    );
    return response.reauth_token;
  }

  async function review(action: RoleChangeReviewAction): Promise<void> {
    if (!selected.value || !pendingSelected.value) return;
    busy.value = true;
    clearMessages();
    try {
      const reauthToken = await grant();
      const input: RoleChangeReviewInput = {
        reasonCode: reviewReason.value,
        reauthToken,
        expectedStatus: "pending",
      };
      const response = action === "approve"
        ? await dependencies.approveRoleChangeRequest(
            selected.value.id,
            input,
            dependencies.accessToken(),
            dependencies.randomUUID(),
          )
        : await dependencies.rejectRoleChangeRequest(
            selected.value.id,
            input,
            dependencies.accessToken(),
            dependencies.randomUUID(),
          );
      success.value = action === "approve"
        ? `角色变更已批准，已撤销 ${response.revoked_session_count} 个目标活跃会话。`
        : "角色变更已拒绝，审计事件已记录。";
      selected.value = response.request;
      await loadRequests({ preserveMessages: true, preserveSelection: true });
    } catch (value) {
      error.value = describeError(value);
    } finally {
      clearCredentials();
      busy.value = false;
    }
  }

  async function createRequest(): Promise<void> {
    clearMessages();
    const targetUserId = createUserId.value.trim();
    if (!targetUserId) {
      error.value = "请输入目标用户 ID";
      clearCredentials();
      return;
    }
    if (createExpectedRole.value === createRequestedRole.value) {
      error.value = "当前角色与申请角色不能相同";
      clearCredentials();
      return;
    }
    busy.value = true;
    try {
      const reauthToken = await grant();
      const response = await dependencies.createRoleChangeRequest(
        targetUserId,
        {
          expectedRole: createExpectedRole.value,
          requestedRole: createRequestedRole.value,
          reasonCode: createReason.value,
          reauthToken,
        },
        dependencies.accessToken(),
        dependencies.randomUUID(),
      );
      success.value = `角色变更请求 ${response.request.id.slice(0, 8)} 已创建，等待另一名管理员复核。`;
      createUserId.value = "";
      filterStatus.value = "pending";
      page.value = 1;
      selected.value = response.request;
      await loadRequests({ preserveMessages: true, preserveSelection: true });
    } catch (value) {
      error.value = describeError(value);
    } finally {
      clearCredentials();
      busy.value = false;
    }
  }

  return {
    items,
    selected,
    filterStatus,
    page,
    total,
    loading,
    busy,
    error,
    success,
    currentPassword,
    totpCode,
    reviewReason,
    createUserId,
    createExpectedRole,
    createRequestedRole,
    createReason,
    totalPages,
    rangeLabel,
    pendingSelected,
    clearCredentials,
    selectRequest,
    loadRequests,
    changeFilter,
    changePage,
    review,
    createRequest,
  };
}
