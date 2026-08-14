<script setup lang="ts">
import type { DesktopAnnouncement, DesktopAnnouncementWriteRequest } from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  archiveDesktopAnnouncement,
  buildDesktopAnnouncementPayload,
  createDesktopAnnouncement,
  listDesktopAnnouncements,
  publishDesktopAnnouncement,
  updateDesktopAnnouncement,
  type DesktopAnnouncementDraft,
} from "../services/desktopAnnouncements";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const items = ref<DesktopAnnouncement[]>([]);
const selectedId = ref<string | null>(null);
const draft = ref<DesktopAnnouncementDraft>(emptyDraft());
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const success = ref("");
const selected = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null);

onMounted(() => void load());

function emptyDraft(): DesktopAnnouncementDraft {
  return {
    title: "",
    content: "",
    contentType: "text",
    imageUrlsText: "",
    actionLabel: "",
    actionUrl: "",
    sortOrder: 0,
    startsAt: "",
    endsAt: "",
  };
}

function selectItem(item: DesktopAnnouncement): void {
  selectedId.value = item.id;
  draft.value = {
    title: item.title,
    content: item.content,
    contentType: item.content_type,
    imageUrlsText: item.image_urls.join("\n"),
    actionLabel: item.action_label ?? "",
    actionUrl: item.action_url ?? "",
    sortOrder: item.sort_order,
    startsAt: item.starts_at ? item.starts_at.slice(0, 16) : "",
    endsAt: item.ends_at ? item.ends_at.slice(0, 16) : "",
  };
  error.value = "";
  success.value = "";
}

function resetDraft(): void {
  selectedId.value = null;
  draft.value = emptyDraft();
  error.value = "";
  success.value = "";
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    items.value = (await listDesktopAnnouncements(auth.accessToken)).items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "公告加载失败";
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const payload: DesktopAnnouncementWriteRequest = buildDesktopAnnouncementPayload(draft.value);
    const result = selected.value
      ? await updateDesktopAnnouncement(auth.accessToken, selected.value.id, payload)
      : await createDesktopAnnouncement(auth.accessToken, payload);
    success.value = selected.value ? "公告草稿已更新。" : "公告草稿已创建。";
    await load();
    selectItem(result);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "公告保存失败";
  } finally {
    busy.value = false;
  }
}

async function publish(): Promise<void> {
  if (!selected.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await publishDesktopAnnouncement(auth.accessToken, selected.value.id);
    success.value = "公告已发布，桌面端将在下次刷新时看到。";
    await load();
    selectItem(result);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "公告发布失败";
  } finally {
    busy.value = false;
  }
}

async function archive(): Promise<void> {
  if (!selected.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await archiveDesktopAnnouncement(auth.accessToken, selected.value.id);
    success.value = "公告已归档，不再向桌面端投放。";
    await load();
    selectItem(result);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "公告归档失败";
  } finally {
    busy.value = false;
  }
}

function statusLabel(status: DesktopAnnouncement["status"]): string {
  return { draft: "草稿", published: "已发布", archived: "已归档" }[status];
}
</script>

<template>
  <section class="space-y-6">
    <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div class="space-y-3">
          <div class="flex flex-wrap gap-2"><Badge>桌面端运营</Badge><Badge variant="outline">公告管理</Badge></div>
          <h1 class="text-3xl font-semibold tracking-tight">桌面端公告管理</h1>
          <p class="max-w-3xl text-muted-foreground">维护桌面端右侧公告栏，支持文字、HTML 说明、图片轮播、跳转按钮、排序和投放时间窗。发布、归档与编辑均写入审计日志。</p>
        </div>
        <div class="flex gap-2"><Button variant="outline" :disabled="loading || busy" @click="load">刷新</Button><Button :disabled="busy" @click="resetDraft">新建公告</Button></div>
      </div>
    </header>

    <div v-if="error" role="alert" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">{{ error }}</div>
    <div v-if="success" role="status" class="rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm">{{ success }}</div>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <section class="rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
        <div class="flex items-center justify-between"><div><h2 class="text-lg font-semibold">公告记录</h2><p class="text-sm text-muted-foreground">草稿不会投放，已归档记录不可再次编辑。</p></div><Badge variant="outline">{{ items.length }} 条</Badge></div>
        <div v-if="loading" class="mt-6 text-sm text-muted-foreground">正在加载公告…</div>
        <div v-else-if="items.length === 0" class="mt-6 rounded-xl border border-dashed p-6 text-sm text-muted-foreground">还没有桌面端公告记录。</div>
        <div v-else class="mt-5 space-y-2">
          <Button v-for="item in items" :key="item.id" type="button" variant="ghost" class="h-auto w-full justify-start rounded-xl border p-4 text-left" :class="selectedId === item.id ? 'border-primary bg-primary/5' : 'border-border'" @click="selectItem(item)">
            <span class="block w-full"><span class="flex items-start justify-between gap-3"><strong class="line-clamp-2">{{ item.title }}</strong><Badge :variant="item.status === 'published' ? 'default' : 'outline'">{{ statusLabel(item.status) }}</Badge></span><span class="mt-2 block line-clamp-2 text-sm font-normal text-muted-foreground">{{ item.content }}</span><span class="mt-3 block text-xs font-normal text-muted-foreground">修订 {{ item.revision }} · 排序 {{ item.sort_order }}</span></span>
          </Button>
        </div>
      </section>

      <section class="rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
        <div class="flex items-start justify-between gap-4"><div><h2 class="text-lg font-semibold">{{ selected ? "编辑公告" : "新建公告草稿" }}</h2><p class="text-sm text-muted-foreground">HTML 只用于受控文本展示，图片地址需使用 HTTPS 或 HTTP。</p></div><Badge v-if="selected" variant="outline">{{ statusLabel(selected.status) }}</Badge></div>
        <form class="mt-5 space-y-5" @submit.prevent="save">
          <div class="space-y-2"><Label for="announcement-title">标题</Label><Input id="announcement-title" v-model="draft.title" maxlength="128" placeholder="例如：桌面端验证规则更新" /></div>
          <div class="space-y-2"><Label for="announcement-content">正文</Label><Textarea id="announcement-content" v-model="draft.content" class="min-h-40" maxlength="20000" placeholder="支持文本或受控 HTML 内容" /></div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2"><Label for="announcement-content-type">内容类型</Label><Select v-model="draft.contentType"><SelectTrigger id="announcement-content-type"><SelectValue placeholder="选择内容类型" /></SelectTrigger><SelectContent><SelectItem value="text">纯文本</SelectItem><SelectItem value="html">HTML</SelectItem></SelectContent></Select></div>
            <div class="space-y-2"><Label for="announcement-order">排序</Label><Input id="announcement-order" v-model.number="draft.sortOrder" type="number" /></div>
          </div>
          <div class="space-y-2"><Label for="announcement-images">图片地址（每行一条，可选）</Label><Textarea id="announcement-images" v-model="draft.imageUrlsText" class="min-h-24" placeholder="https://synthetic.example/notice.png" /></div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2"><Label for="announcement-action-label">按钮文字（可选）</Label><Input id="announcement-action-label" v-model="draft.actionLabel" maxlength="64" /></div>
            <div class="space-y-2"><Label for="announcement-action-url">按钮地址（可选）</Label><Input id="announcement-action-url" v-model="draft.actionUrl" placeholder="https://synthetic.example" /></div>
          </div>
          <div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="announcement-starts">开始时间（可选）</Label><Input id="announcement-starts" v-model="draft.startsAt" type="datetime-local" /></div><div class="space-y-2"><Label for="announcement-ends">结束时间（可选）</Label><Input id="announcement-ends" v-model="draft.endsAt" type="datetime-local" /></div></div>
          <div class="flex flex-wrap gap-2"><Button type="submit" :disabled="busy || selected?.status === 'archived'">{{ busy ? "处理中…" : "保存草稿" }}</Button><Button v-if="selected && selected.status !== 'published' && selected.status !== 'archived'" type="button" variant="secondary" :disabled="busy" @click="publish">发布公告</Button><Button v-if="selected && selected.status !== 'archived'" type="button" variant="outline" :disabled="busy" @click="archive">归档</Button></div>
        </form>
      </section>
    </div>
  </section>
</template>
