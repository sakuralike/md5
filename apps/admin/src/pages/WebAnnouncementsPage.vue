<script setup lang="ts">
import type { WebAnnouncement, WebAnnouncementWriteRequest } from "@password-detective/api-contract";
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
  archiveWebAnnouncement,
  buildWebAnnouncementPayload,
  createWebAnnouncement,
  listWebAnnouncements,
  publishWebAnnouncement,
  updateWebAnnouncement,
  uploadWebAnnouncementImage,
  type WebAnnouncementDraft,
} from "../services/webAnnouncements";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const items = ref<WebAnnouncement[]>([]);
const selectedId = ref<string | null>(null);
const draft = ref<WebAnnouncementDraft>(emptyDraft());
const loading = ref(true);
const busy = ref(false);
const uploadBusy = ref(false);
const error = ref("");
const uploadError = ref("");
const success = ref("");
const selected = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null);
const imageUrls = computed(() =>
  draft.value.imageUrlsText
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean),
);

onMounted(() => void load());

function emptyDraft(): WebAnnouncementDraft {
  return {
    title: "",
    content: "",
    contentType: "text",
    imageUrlsText: "",
    actionLabel: "",
    actionUrl: "",
    sortOrder: 0,
    autoCloseSeconds: 10,
    startsAt: "",
    endsAt: "",
  };
}

function selectItem(item: WebAnnouncement, clearFeedback = true): void {
  selectedId.value = item.id;
  draft.value = {
    title: item.title,
    content: item.content,
    contentType: item.content_type,
    imageUrlsText: item.image_urls.join("\n"),
    actionLabel: item.action_label ?? "",
    actionUrl: item.action_url ?? "",
    sortOrder: item.sort_order,
    autoCloseSeconds: item.auto_close_seconds ?? 0,
    startsAt: item.starts_at ? item.starts_at.slice(0, 16) : "",
    endsAt: item.ends_at ? item.ends_at.slice(0, 16) : "",
  };
  if (clearFeedback) {
    error.value = "";
    uploadError.value = "";
    success.value = "";
  }
}

function resetDraft(): void {
  selectedId.value = null;
  draft.value = emptyDraft();
  error.value = "";
  uploadError.value = "";
  success.value = "";
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    items.value = (await listWebAnnouncements(auth.accessToken)).items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "公告加载失败";
  } finally {
    loading.value = false;
  }
}

async function handleImageUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = "";
  if (files.length === 0) return;
  uploadError.value = "";

  const current = imageUrls.value;
  if (current.length + files.length > 8) {
    uploadError.value = "单条公告最多上传 8 张图片";
    return;
  }
  const invalid = files.find(
    (file) => !["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024,
  );
  if (invalid) {
    uploadError.value = "图片仅支持 PNG、JPEG、WebP，单张不能超过 5 MB";
    return;
  }

  uploadBusy.value = true;
  try {
    const uploaded: string[] = [];
    for (const file of files) {
      const result = await uploadWebAnnouncementImage(auth.accessToken, file);
      uploaded.push(result.url);
    }
    draft.value.imageUrlsText = [...current, ...uploaded].join("\n");
    success.value = `已上传 ${uploaded.length} 张公告图片，请保存草稿。`;
  } catch (caught) {
    uploadError.value = caught instanceof Error ? caught.message : "公告图片上传失败";
  } finally {
    uploadBusy.value = false;
  }
}

function removeImage(url: string): void {
  draft.value.imageUrlsText = imageUrls.value.filter((item) => item !== url).join("\n");
}

async function save(): Promise<void> {
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const payload: WebAnnouncementWriteRequest = buildWebAnnouncementPayload(draft.value);
    const result = selected.value
      ? await updateWebAnnouncement(auth.accessToken, selected.value.id, payload)
      : await createWebAnnouncement(auth.accessToken, payload);
    const message = selected.value ? "公告草稿已更新。" : "公告草稿已创建。";
    await load();
    selectItem(result, false);
    success.value = message;
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
    const result = await publishWebAnnouncement(auth.accessToken, selected.value.id);
    await load();
    selectItem(result, false);
    success.value = "公告已发布，Web 端将在下次请求时看到。";
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
    const result = await archiveWebAnnouncement(auth.accessToken, selected.value.id);
    await load();
    selectItem(result, false);
    success.value = "公告已归档，不再向 Web 端投放。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "公告归档失败";
  } finally {
    busy.value = false;
  }
}

function statusLabel(status: WebAnnouncement["status"]): string {
  return { draft: "草稿", published: "已发布", archived: "已归档" }[status];
}
</script>

<template>
  <section class="space-y-6">
    <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div class="space-y-3">
          <div class="flex flex-wrap gap-2"><Badge>Web 端运营</Badge><Badge variant="outline">公告管理</Badge></div>
          <h1 class="text-3xl font-semibold tracking-tight">Web 端公告管理</h1>
          <p class="max-w-3xl text-muted-foreground">独立发布到网站右下角弹窗，支持纯文本、受控 HTML、图片、跳转链接和自动关闭时间。</p>
        </div>
        <Button type="button" variant="outline" @click="resetDraft">新建公告</Button>
      </div>
    </header>

    <p v-if="error" class="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{{ error }}</p>
    <p v-if="success" class="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-700">{{ success }}</p>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <section class="rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
        <div class="flex items-center justify-between"><div><h2 class="text-lg font-semibold">公告记录</h2><p class="text-sm text-muted-foreground">草稿不会投放，已归档记录不可再次编辑。</p></div><Badge variant="outline">{{ items.length }} 条</Badge></div>
        <div v-if="loading" class="mt-6 text-sm text-muted-foreground">正在加载公告…</div>
        <div v-else-if="items.length === 0" class="mt-6 rounded-xl border border-dashed p-6 text-sm text-muted-foreground">还没有 Web 端公告记录。</div>
        <div v-else class="mt-5 space-y-2">
          <Button v-for="item in items" :key="item.id" type="button" variant="ghost" class="h-auto w-full justify-start rounded-xl border p-4 text-left" :class="selectedId === item.id ? 'border-primary bg-primary/5' : 'border-border'" @click="selectItem(item)">
            <span class="block w-full"><span class="flex items-start justify-between gap-3"><strong class="line-clamp-2">{{ item.title }}</strong><Badge :variant="item.status === 'published' ? 'default' : 'outline'">{{ statusLabel(item.status) }}</Badge></span><span class="mt-2 block line-clamp-2 text-sm font-normal text-muted-foreground">{{ item.content }}</span><span class="mt-3 block text-xs font-normal text-muted-foreground">修订 {{ item.revision }} · 图片 {{ item.image_urls.length }} 张 · 排序 {{ item.sort_order }} · {{ item.auto_close_seconds ? `${item.auto_close_seconds} 秒自动关闭` : "不自动关闭" }}</span></span>
          </Button>
        </div>
      </section>

      <section class="rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
        <div class="flex items-start justify-between gap-4"><div><h2 class="text-lg font-semibold">{{ selected ? "编辑公告" : "新建公告草稿" }}</h2><p class="text-sm text-muted-foreground">图片上传后会生成 Web 公告专用静态资源地址，网站弹窗下次请求即可加载。</p></div><Badge v-if="selected" variant="outline">{{ statusLabel(selected.status) }}</Badge></div>
        <form class="mt-5 space-y-5" @submit.prevent="save">
          <div class="space-y-2"><Label for="announcement-title">标题</Label><Input id="announcement-title" v-model="draft.title" maxlength="128" placeholder="例如：网站维护窗口提醒" /></div>
          <div class="space-y-2"><Label for="announcement-content">正文</Label><Textarea id="announcement-content" v-model="draft.content" class="min-h-40" maxlength="20000" placeholder="支持文本或受控 HTML 内容" /></div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2"><Label for="announcement-content-type">内容类型</Label><Select v-model="draft.contentType"><SelectTrigger id="announcement-content-type"><SelectValue placeholder="选择内容类型" /></SelectTrigger><SelectContent><SelectItem value="text">纯文本</SelectItem><SelectItem value="html">HTML</SelectItem></SelectContent></Select></div>
            <div class="space-y-2"><Label for="announcement-order">排序</Label><Input id="announcement-order" v-model.number="draft.sortOrder" type="number" /></div>
          </div>
          <div class="space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-3"><Label for="announcement-images">公告图片</Label><span class="text-xs text-muted-foreground">PNG/JPEG/WebP，单张不超过 5 MB，最多 8 张</span></div>
            <Input id="announcement-images" type="file" accept="image/png,image/jpeg,image/webp" multiple :disabled="uploadBusy || selected?.status === 'archived'" @change="handleImageUpload" />
            <p v-if="uploadBusy" class="text-sm text-muted-foreground">正在上传图片，请稍候…</p>
            <p v-if="uploadError" class="text-sm text-destructive">{{ uploadError }}</p>
            <div v-if="imageUrls.length" class="grid gap-3 sm:grid-cols-2">
              <div v-for="url in imageUrls" :key="url" class="overflow-hidden rounded-xl border bg-muted/20">
                <img :src="url" alt="公告图片预览" class="h-32 w-full object-cover" />
                <div class="flex items-center justify-between gap-2 p-2"><span class="truncate text-xs text-muted-foreground">{{ url }}</span><Button type="button" variant="ghost" size="sm" :disabled="selected?.status === 'archived'" @click="removeImage(url)">移除</Button></div>
              </div>
            </div>
            <Textarea v-model="draft.imageUrlsText" class="min-h-20" placeholder="也可以手动填写 HTTP(S) 或已上传图片地址；每行一条" />
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2"><Label for="announcement-action-label">图片链接说明（可选）</Label><Input id="announcement-action-label" v-model="draft.actionLabel" maxlength="64" placeholder="例如：查看活动详情" /></div>
            <div class="space-y-2"><Label for="announcement-action-url">图片点击链接（可选）</Label><Input id="announcement-action-url" v-model="draft.actionUrl" placeholder="https://synthetic.example/notice" /><p class="text-xs text-muted-foreground">网站用户点击公告图片时打开；留空则图片仅展示。</p></div>
          </div>
          <div class="space-y-2">
            <Label for="announcement-auto-close">自动关闭秒数</Label>
            <Input id="announcement-auto-close" v-model.number="draft.autoCloseSeconds" type="number" min="0" max="86400" step="1" />
            <p class="text-xs text-muted-foreground">设置为 0 时不自动关闭；1–86400 秒时，Web 弹窗会在对应时间后自动隐藏。</p>
          </div>
          <div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="announcement-starts">开始时间（可选）</Label><Input id="announcement-starts" v-model="draft.startsAt" type="datetime-local" /></div><div class="space-y-2"><Label for="announcement-ends">结束时间（可选）</Label><Input id="announcement-ends" v-model="draft.endsAt" type="datetime-local" /></div></div>
          <div class="flex flex-wrap gap-2"><Button type="submit" :disabled="busy || uploadBusy || selected?.status === 'archived'">{{ busy ? "处理中…" : "保存草稿" }}</Button><Button v-if="selected && selected.status !== 'published' && selected.status !== 'archived'" type="button" variant="secondary" :disabled="busy || uploadBusy" @click="publish">发布公告</Button><Button v-if="selected && selected.status !== 'archived'" type="button" variant="outline" :disabled="busy || uploadBusy" @click="archive">归档</Button></div>
        </form>
      </section>
    </div>
  </section>
</template>
