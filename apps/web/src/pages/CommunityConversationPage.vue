<script setup lang="ts">
import type { CommunityDirectMessageResponse } from "@password-detective/api-contract";
import { computed, onBeforeUnmount, onMounted, onServerPrefetch, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { createClientId } from "@/lib/clientId";
import {
  createCommunityIdempotencyKey,
  listCommunityDirectMessages,
  reportCommunityDirectMessage,
  sendCommunityDirectMessage,
  updateCommunityDirectReadState,
} from "../services/community";
import { useAuthStore } from "../stores/auth";
import { useCommunityDirectMessagesStore } from "../stores/communityDirectMessages";

const route = useRoute();
const auth = useAuthStore();
const directMessages = useCommunityDirectMessagesStore();
const messages = ref<CommunityDirectMessageResponse[]>([]);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const loadingMore = ref(false);
const sending = ref(false);
const body = ref("");
const error = ref("");
const reportMessageId = ref<string | null>(null);
const reportReason = ref<"spam" | "harassment" | "privacy" | "unsafe" | "other">("harassment");
const reportDetails = ref("");
const reporting = ref(false);
const reportSuccess = ref("");
const counterpartLastReadSequence = ref(0);
let refreshTimer: ReturnType<typeof setTimeout> | null = null;
let loadRequestId = 0;

const conversationId = computed(() => String(route.params.conversationId ?? ""));
const orderedMessages = computed(() =>
  [...messages.value].sort((left, right) => left.sequence - right.sequence),
);
const effectiveCounterpartLastReadSequence = computed(() =>
  Math.max(
    counterpartLastReadSequence.value,
    directMessages.counterpartReadSequence[conversationId.value] ?? 0,
  ),
);

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function isOwnMessage(message: CommunityDirectMessageResponse): boolean {
  return message.sender_username === auth.user?.username;
}

async function markLoadedMessagesRead(
  loaded: CommunityDirectMessageResponse[],
  currentLastReadSequence: number,
): Promise<void> {
  const lastReadSequence = loaded.reduce(
    (maximum, message) => Math.max(maximum, message.sequence),
    0,
  );
  if (
    !conversationId.value ||
    lastReadSequence === 0 ||
    lastReadSequence <= currentLastReadSequence
  ) return;
  await updateCommunityDirectReadState(
    conversationId.value,
    { last_read_sequence: lastReadSequence },
    auth.accessToken,
    createCommunityIdempotencyKey("direct-read-state"),
  );
}

async function load(reset = true): Promise<void> {
  if (!conversationId.value) return;
  const requestId = ++loadRequestId;
  const requestedConversationId = conversationId.value;
  if (reset && messages.value.length === 0) loading.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const response = await listCommunityDirectMessages(
      conversationId.value,
      auth.accessToken,
      {
        ...(reset || !nextCursor.value ? {} : { cursor: nextCursor.value }),
        limit: 30,
      },
    );
    if (requestId !== loadRequestId || requestedConversationId !== conversationId.value) return;
    const incoming = reset ? response.items : [...messages.value, ...response.items];
    messages.value = mergeMessages(incoming);
    counterpartLastReadSequence.value = Math.max(
      counterpartLastReadSequence.value,
      response.counterpart_last_read_sequence,
    );
    nextCursor.value = response.next_cursor;
    hasMore.value = response.has_more;
    if (reset) await markLoadedMessagesRead(response.items, response.last_read_sequence);
  } catch (caught) {
    if (requestId !== loadRequestId || requestedConversationId !== conversationId.value) return;
    error.value = caught instanceof Error ? caught.message : "无法加载私信会话";
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false;
      loadingMore.value = false;
    }
  }
}

async function send(): Promise<void> {
  const normalizedBody = body.value.trim();
  if (!conversationId.value || !normalizedBody || sending.value) return;
  sending.value = true;
  error.value = "";
  try {
    const message = await sendCommunityDirectMessage(
      conversationId.value,
      { body: normalizedBody, client_message_id: createClientId() },
      auth.accessToken,
      createCommunityIdempotencyKey("direct-message"),
    );
    messages.value = [message, ...messages.value.filter((item) => item.id !== message.id)];
    body.value = "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "发送私信失败";
  } finally {
    sending.value = false;
  }
}

async function reportMessage(): Promise<void> {
  if (!reportMessageId.value || reportDetails.value.trim().length < 10 || reporting.value) return;
  reporting.value = true;
  error.value = "";
  reportSuccess.value = "";
  try {
    await reportCommunityDirectMessage(
      reportMessageId.value,
      { reason: reportReason.value, details: reportDetails.value.trim() },
      auth.accessToken,
      createCommunityIdempotencyKey("direct-message-report"),
    );
    reportSuccess.value = "消息举报已提交，管理员将在受控案件中复核。";
    reportDetails.value = "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "消息举报失败";
  } finally {
    reporting.value = false;
  }
}

function mergeMessages(items: CommunityDirectMessageResponse[]): CommunityDirectMessageResponse[] {
  const byId = new Map<string, CommunityDirectMessageResponse>();
  for (const item of items) byId.set(item.id, item);
  return [...byId.values()];
}

function scheduleRealtimeRefresh(): void {
  if (refreshTimer !== null) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    void load();
  }, 100);
}

watch(
  () => [
    directMessages.resetRevision,
    directMessages.conversationMessageRevision[conversationId.value] ?? 0,
  ],
  scheduleRealtimeRefresh,
);

onMounted(() => void load());
onServerPrefetch(() => load());
onBeforeUnmount(() => {
  loadRequestId += 1;
  if (refreshTimer !== null) clearTimeout(refreshTimer);
});
</script>

<template>
  <section class="mx-auto max-w-4xl space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Direct message</p>
        <h1 class="text-3xl font-semibold tracking-tight text-foreground">私信会话</h1>
        <p class="max-w-2xl text-sm leading-6 text-muted-foreground">
          消息正文采用服务端信封加密存储。当前不是端到端加密，请勿发送密码、令牌或其他敏感信息。
        </p>
      </div>
      <Button as-child variant="outline">
        <RouterLink to="/community/messages">返回私信收件箱</RouterLink>
      </Button>
    </div>

    <Alert v-if="error" variant="destructive" role="alert">
      <AlertTitle>私信会话暂时不可用</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Card>
      <CardHeader>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>消息记录</CardTitle>
            <CardDescription>仅会话成员可读取，较早消息可按游标继续加载。</CardDescription>
          </div>
          <Badge variant="outline">{{ orderedMessages.length }} 条已加载</Badge>
        </div>
      </CardHeader>
      <CardContent class="space-y-4">
        <div v-if="hasMore" class="flex justify-center">
          <Button variant="outline" :disabled="loadingMore" @click="load(false)">
            {{ loadingMore ? "加载中…" : "加载更早消息" }}
          </Button>
        </div>

        <div v-if="loading" class="space-y-3" aria-label="正在加载私信消息">
          <div v-for="index in 3" :key="index" class="h-20 animate-pulse rounded-xl bg-muted" />
        </div>
        <div v-else class="space-y-3" aria-live="polite">
          <article
            v-for="message in orderedMessages"
            :key="message.id"
            class="max-w-[88%] space-y-1 rounded-xl border p-3 sm:max-w-[75%]"
            :class="isOwnMessage(message) ? 'ml-auto bg-primary text-primary-foreground' : 'bg-muted'"
          >
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span class="font-semibold">{{ isOwnMessage(message) ? "我" : `@${message.sender_username}` }}</span>
              <span :class="isOwnMessage(message) ? 'text-primary-foreground/80' : 'text-muted-foreground'">
                {{ formatDate(message.created_at) }}
              </span>
            </div>
            <p class="whitespace-pre-wrap break-words text-sm leading-6">{{ message.body }}</p>
            <Badge
              v-if="isOwnMessage(message)"
              variant="secondary"
              class="mt-2"
            >
              {{
                message.sequence <= effectiveCounterpartLastReadSequence
                  ? "对方已读"
                  : "已发送"
              }}
            </Badge>
            <Button
              v-if="!isOwnMessage(message)"
              type="button"
              size="sm"
              variant="ghost"
              class="mt-2"
              @click="reportMessageId = message.id; reportSuccess = ''"
            >
              举报消息
            </Button>
          </article>

          <div
            v-if="orderedMessages.length === 0"
            class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground"
          >
            尚无消息。发送第一条合成、非敏感内容开始会话。
          </div>
        </div>
      </CardContent>
    </Card>

    <Card v-if="reportMessageId">
      <CardHeader>
        <CardTitle>举报私信消息</CardTitle>
        <CardDescription>仅提交最小化举报说明，管理员将在受控案件上下文中复核。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="space-y-2">
          <Label for="community-direct-message-report-reason">举报原因</Label>
          <Select v-model="reportReason">
            <SelectTrigger id="community-direct-message-report-reason">
              <SelectValue placeholder="选择举报原因" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="spam">垃圾广告</SelectItem>
              <SelectItem value="harassment">骚扰攻击</SelectItem>
              <SelectItem value="privacy">隐私泄露</SelectItem>
              <SelectItem value="unsafe">不安全内容</SelectItem>
              <SelectItem value="other">其他问题</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label for="community-direct-message-report-details">问题说明</Label>
          <Textarea
            id="community-direct-message-report-details"
            v-model="reportDetails"
            :maxlength="1000"
            placeholder="请用至少 10 个字说明需要复核的原因…"
          />
        </div>
        <div class="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="ghost" @click="reportMessageId = null">取消</Button>
          <Button type="button" :disabled="reporting || reportDetails.trim().length < 10" @click="reportMessage">
            {{ reporting ? "提交中…" : "提交举报" }}
          </Button>
        </div>
        <p v-if="reportSuccess" role="status" class="text-sm text-muted-foreground">{{ reportSuccess }}</p>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>发送消息</CardTitle>
        <CardDescription>最多 4000 个字符；发送期间会禁用按钮以避免重复提交。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="space-y-2">
          <Label for="community-direct-message-body">消息内容</Label>
          <Textarea
            id="community-direct-message-body"
            v-model="body"
            class="min-h-32"
            :maxlength="4000"
            placeholder="请输入不含密码、令牌或个人敏感信息的消息…"
          />
          <p class="text-right text-xs text-muted-foreground">{{ body.length }}/4000</p>
        </div>
        <div class="flex justify-end">
          <Button :disabled="sending || !body.trim()" @click="send">
            {{ sending ? "发送中…" : "发送消息" }}
          </Button>
        </div>
      </CardContent>
    </Card>
  </section>
</template>
