<script setup lang="ts">
import type {
  CommunitySearchProviderState,
  CommunitySearchResultItem,
  CommunitySearchResultType,
} from "@password-detective/api-contract";
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { getPublicSearchSuggestions, type SearchSuggestion } from "@/lib/searchSuggestions";
import { searchCommunity } from "../services/community";
import { useAuthStore } from "../stores/auth";

const PAGE_SIZE = 20;
const SEARCH_TYPES: Array<{ value: CommunitySearchResultType; label: string }> = [
  { value: "post", label: "主题" },
  { value: "user", label: "用户" },
  { value: "board", label: "板块" },
  { value: "group", label: "群组" },
];

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const query = ref(readQuery(route.query.q));
const selectedTypes = ref<CommunitySearchResultType[]>(readTypes(route.query.types));
const currentPage = ref(readPage(route.query.page));
const items = ref<CommunitySearchResultItem[]>([]);
const total = ref(0);
const provider = ref<CommunitySearchProviderState | null>(null);
const loading = ref(false);
const searched = ref(false);
const error = ref("");
const suggestionsOpen = ref(false);
const activeSuggestionIndex = ref(-1);

const canSearch = computed(() => query.value.trim().length >= 2);
const hasPreviousPage = computed(() => currentPage.value > 1);
const hasNextPage = computed(() => currentPage.value * PAGE_SIZE < total.value);
const suggestions = computed(() => getPublicSearchSuggestions(query.value));
const visibleSuggestions = computed(() => suggestionsOpen.value && suggestions.value.length > 0 ? suggestions.value : []);
const activeSuggestionId = computed(() => {
  const suggestion = visibleSuggestions.value[activeSuggestionIndex.value];
  return suggestion ? `community-search-suggestion-${suggestion.id}` : undefined;
});

onMounted(() => {
  if (canSearch.value) void loadSearch();
});

watch(
  () => [route.query.q, route.query.types, route.query.page],
  () => {
    query.value = readQuery(route.query.q);
    selectedTypes.value = readTypes(route.query.types);
    currentPage.value = readPage(route.query.page);
    if (query.value.trim().length >= 2) {
      void loadSearch();
    } else {
      items.value = [];
      total.value = 0;
      provider.value = null;
      searched.value = false;
    }
  },
);

async function submitSearch(): Promise<void> {
  const normalizedQuery = query.value.trim();
  if (normalizedQuery.length < 2) {
    error.value = "请输入至少 2 个字符后再搜索。";
    return;
  }
  suggestionsOpen.value = false;
  activeSuggestionIndex.value = -1;
  await updateRoute(1);
}

function openSuggestions(): void {
  suggestionsOpen.value = true;
  activeSuggestionIndex.value = -1;
}

function updateSuggestionQuery(): void {
  activeSuggestionIndex.value = -1;
  suggestionsOpen.value = true;
}

function selectSuggestion(suggestion: SearchSuggestion): void {
  query.value = suggestion.value;
  suggestionsOpen.value = false;
  activeSuggestionIndex.value = -1;
}

function handleSuggestionKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    suggestionsOpen.value = false;
    activeSuggestionIndex.value = -1;
    return;
  }
  if (!visibleSuggestions.value.length) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    activeSuggestionIndex.value = (activeSuggestionIndex.value + 1) % visibleSuggestions.value.length;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    activeSuggestionIndex.value = activeSuggestionIndex.value <= 0
      ? visibleSuggestions.value.length - 1
      : activeSuggestionIndex.value - 1;
  } else if (event.key === "Enter" && activeSuggestionIndex.value >= 0) {
    event.preventDefault();
    const suggestion = visibleSuggestions.value[activeSuggestionIndex.value];
    if (suggestion) selectSuggestion(suggestion);
  }
}

function suggestionKindLabel(kind: SearchSuggestion["kind"]): string {
  return { algorithm: "算法", board: "板块", filter: "筛选", navigation: "导航" }[kind];
}

async function goToPage(page: number): Promise<void> {
  if (page < 1 || page === currentPage.value) return;
  await updateRoute(page);
}

async function updateRoute(page: number): Promise<void> {
  await router.replace({
    query: {
      q: query.value.trim(),
      types: selectedTypes.value.length > 0 ? selectedTypes.value : undefined,
      page: page > 1 ? String(page) : undefined,
    },
  });
}

function toggleType(type: CommunitySearchResultType, checked: boolean): void {
  selectedTypes.value = checked
    ? [...selectedTypes.value, type]
    : selectedTypes.value.filter((value) => value !== type);
}

async function loadSearch(): Promise<void> {
  const normalizedQuery = query.value.trim();
  if (normalizedQuery.length < 2) return;
  loading.value = true;
  searched.value = true;
  error.value = "";
  try {
    const response = await searchCommunity(
      {
        query: normalizedQuery,
        types: selectedTypes.value,
        page: currentPage.value,
        pageSize: PAGE_SIZE,
      },
      auth.isAuthenticated ? auth.accessToken : undefined,
    );
    items.value = response.items;
    total.value = response.total;
    provider.value = response.provider;
  } catch (caught) {
    items.value = [];
    total.value = 0;
    error.value = caught instanceof Error ? caught.message : "社区搜索暂时不可用";
  } finally {
    loading.value = false;
  }
}

function destinationFor(item: CommunitySearchResultItem): string {
  if (item.type === "post") return `/community/posts/${item.source_id}`;
  if (item.type === "user" && item.username) return `/community/users/${item.username}`;
  if (item.type === "board" && item.board_code) return `/community?board=${item.board_code}`;
  if (item.type === "group" && item.group_slug) return `/community/groups/${item.group_slug}`;
  return "/community";
}

function typeLabel(type: CommunitySearchResultType): string {
  return SEARCH_TYPES.find((item) => item.value === type)?.label ?? "社区内容";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value));
}

function readQuery(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readTypes(value: unknown): CommunitySearchResultType[] {
  const rawTypes = Array.isArray(value) ? value : typeof value === "string" ? [value] : [];
  return rawTypes.filter((type): type is CommunitySearchResultType =>
    SEARCH_TYPES.some((item) => item.value === type),
  );
}

function readPage(value: unknown): number {
  const parsed = typeof value === "string" ? Number.parseInt(value, 10) : Number.NaN;
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1;
}
</script>

<template>
  <section class="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
    <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div class="space-y-3">
          <div class="flex flex-wrap gap-2"><Badge>公开内容</Badge><Badge variant="outline">权限复核</Badge></div>
          <h1 class="text-3xl font-semibold tracking-tight">搜索社区</h1>
          <p class="max-w-3xl text-muted-foreground">检索公开主题、用户、板块和公开群组。登录后仍只显示您有权查看的内容。</p>
        </div>
        <Button variant="outline" as-child><RouterLink to="/community">返回社区首页</RouterLink></Button>
      </div>
    </header>

    <Card>
      <CardHeader>
        <CardTitle>搜索条件</CardTitle>
        <CardDescription>输入至少 2 个字符，可按内容类型收窄结果。公开搜索建议只来自审核过的算法、板块、筛选项和导航词。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-5">
        <form class="flex flex-col gap-3 sm:flex-row" @submit.prevent="submitSearch">
          <div class="relative min-w-0 flex-1">
            <Input
              id="community-search-query"
              v-model="query"
              role="combobox"
              aria-label="搜索社区"
              aria-autocomplete="list"
              aria-controls="community-search-suggestions"
              :aria-expanded="visibleSuggestions.length > 0"
              :aria-activedescendant="activeSuggestionId"
              placeholder="例如：恢复指南、数据安全"
              @focus="openSuggestions"
              @input="updateSuggestionQuery"
              @keydown="handleSuggestionKeydown"
              @blur="suggestionsOpen = false"
            />
            <div
              v-if="visibleSuggestions.length"
              id="community-search-suggestions"
              class="absolute inset-x-0 top-full z-20 mt-2 overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
              role="listbox"
              aria-label="公开搜索建议"
            >
              <Button
                v-for="(suggestion, index) in visibleSuggestions"
                :id="`community-search-suggestion-${suggestion.id}`"
                :key="suggestion.id"
                variant="ghost"
                class="h-auto w-full justify-start rounded-sm px-3 py-2 text-left"
                role="option"
                :aria-selected="activeSuggestionIndex === index"
                type="button"
                @mousedown.prevent="selectSuggestion(suggestion)"
              >
                <span class="min-w-0 flex-1"><strong class="block truncate">{{ suggestion.label }}</strong><small class="block text-muted-foreground">{{ suggestion.description }}</small></span>
                <Badge variant="outline">{{ suggestionKindLabel(suggestion.kind) }}</Badge>
              </Button>
            </div>
          </div>
          <Button type="submit" :disabled="loading || !canSearch">{{ loading ? "搜索中…" : "搜索" }}</Button>
        </form>
        <div class="flex flex-wrap gap-x-5 gap-y-3">
          <label v-for="searchType in SEARCH_TYPES" :key="searchType.value" class="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              :model-value="selectedTypes.includes(searchType.value)"
              @update:model-value="toggleType(searchType.value, Boolean($event))"
            />
            <span>{{ searchType.label }}</span>
          </label>
        </div>
      </CardContent>
    </Card>

    <Alert v-if="error" variant="destructive"><AlertTitle>搜索失败</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
    <Alert v-if="provider?.degraded" variant="default"><AlertTitle>搜索已降级</AlertTitle><AlertDescription>当前使用受限的前缀匹配模式，结果覆盖范围可能较小。</AlertDescription></Alert>

    <Card>
      <CardHeader class="flex flex-row items-start justify-between gap-4">
        <div><CardTitle>搜索结果</CardTitle><CardDescription>{{ searched ? `共找到 ${total} 条公开结果` : "请输入关键词开始搜索" }}</CardDescription></div>
        <Badge v-if="provider" variant="outline">{{ provider.mode }}</Badge>
      </CardHeader>
      <CardContent class="space-y-3">
        <div v-if="loading" class="space-y-3"><div v-for="index in 3" :key="index" class="h-28 animate-pulse rounded-xl bg-muted" /></div>
        <div v-else-if="items.length === 0" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">没有找到公开结果。请调整关键词或筛选条件后重试。</div>
        <RouterLink v-for="item in items" v-else :key="`${item.type}-${item.source_id}`" :to="destinationFor(item)" class="block rounded-xl border p-4 transition-colors hover:bg-muted/50">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"><div class="min-w-0 space-y-2"><div class="flex flex-wrap items-center gap-2"><Badge variant="secondary">{{ typeLabel(item.type) }}</Badge><h2 class="truncate font-semibold">{{ item.title }}</h2></div><p class="line-clamp-2 text-sm text-muted-foreground">{{ item.preview || "暂无公开摘要" }}</p><p class="text-xs text-muted-foreground">{{ item.username ? `${item.username} · ` : "" }}更新于 {{ formatDate(item.updated_at) }}</p></div><span class="shrink-0 text-sm text-primary">查看详情 →</span></div>
        </RouterLink>
      </CardContent>
    </Card>

    <div v-if="searched && total > 0" class="flex items-center justify-between gap-3">
      <Button variant="outline" :disabled="!hasPreviousPage || loading" @click="goToPage(currentPage - 1)">上一页</Button>
      <p class="text-sm text-muted-foreground">第 {{ currentPage }} 页</p>
      <Button variant="outline" :disabled="!hasNextPage || loading" @click="goToPage(currentPage + 1)">下一页</Button>
    </div>
  </section>
</template>
