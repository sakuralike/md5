<script setup lang="ts">
import { createClientId } from "@/lib/clientId";
import { ApiError } from "@password-detective/api-contract";
import type {
  OperationalSettingsSnapshot,
  SettingVersionDetail,
  UserLevelDefinition,
} from "@password-detective/api-contract";
import { BadgeCheck, Plus, RefreshCw, Save, Trash2 } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createSettingVersion,
  getSettingVersion,
  listSettingVersions,
} from "../services/settings";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const base = ref<SettingVersionDetail | null>(null);
const levels = ref<UserLevelDefinition[]>([]);
const publishedVersionId = ref<string | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const success = ref("");

function describeError(value: unknown): string {
  if (value instanceof ApiError) return value.message;
  if (value instanceof Error) return value.message;
  return "用户等级配置加载失败，请稍后重试。";
}

function cloneLevels(value: UserLevelDefinition[]): UserLevelDefinition[] {
  return value.map((level) => ({ ...level }));
}

async function loadLevels(): Promise<void> {
  if (!auth.accessToken) return;
  loading.value = true;
  error.value = "";
  success.value = "";
  try {
    const versions = await listSettingVersions(auth.accessToken, 1, 50);
    publishedVersionId.value = versions.published_version_id;
    const preferred = versions.items.find((item) => item.status === "draft")?.id
      ?? versions.published_version_id
      ?? versions.items[0]?.id;
    if (!preferred) {
      base.value = null;
      levels.value = [];
      return;
    }
    base.value = await getSettingVersion(preferred, auth.accessToken);
    levels.value = cloneLevels(base.value.snapshot.user_levels);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

function addLevel(): void {
  let sequence = levels.value.length + 1;
  let code = `custom_${sequence}`;
  while (levels.value.some((item) => item.code === code)) {
    sequence += 1;
    code = `custom_${sequence}`;
  }
  const previous = levels.value.at(-1);
  levels.value.push({
    code,
    name: `自定义等级 ${sequence}`,
    description: "请填写该等级的成长目标与用户权益。",
    min_growth_points: (previous?.min_growth_points ?? 0) + 100,
    daily_reveal_quota: previous?.daily_reveal_quota ?? 20,
    can_submit: true,
  });
}

function removeLevel(index: number): void {
  if (levels.value.length <= 1) return;
  levels.value.splice(index, 1);
  levels.value.sort((left, right) => left.min_growth_points - right.min_growth_points);
  levels.value[0].min_growth_points = 0;
}

function normalizedSnapshot(): OperationalSettingsSnapshot | null {
  if (!base.value || levels.value.length === 0) return null;
  const normalizedLevels = cloneLevels(levels.value)
    .map((level) => ({
      ...level,
      code: level.code.trim(),
      name: level.name.trim(),
      description: level.description.trim(),
      min_growth_points: Number(level.min_growth_points),
      daily_reveal_quota: Number(level.daily_reveal_quota),
    }))
    .sort((left, right) => left.min_growth_points - right.min_growth_points);
  normalizedLevels[0].min_growth_points = 0;
  return {
    ...base.value.snapshot,
    site_navigation: base.value.snapshot.site_navigation.map((item) => ({ ...item })),
    user_levels: normalizedLevels,
  };
}

async function saveDraft(): Promise<void> {
  if (!auth.accessToken) return;
  const snapshot = normalizedSnapshot();
  if (!snapshot) {
    error.value = "当前没有可保存的等级配置基线。";
    return;
  }
  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    const response = await createSettingVersion(
      {
        expectedBaseVersionId: publishedVersionId.value,
        reasonCode: "product_policy",
        snapshot,
      },
      auth.accessToken,
      `admin-user-levels-${createClientId()}`,
    );
    base.value = response.version;
    levels.value = cloneLevels(response.version.snapshot.user_levels);
    success.value = "用户等级与权益已保存为不可变草稿，请在系统配置的发布门禁中确认并发布。";
  } catch (value) {
    error.value = describeError(value);
  } finally {
    saving.value = false;
  }
}

onMounted(() => void loadLevels());
</script>

<template>
  <section id="user-levels" class="scroll-mt-28 space-y-5 rounded-2xl border bg-card p-5 text-card-foreground shadow-sm">
    <header class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 class="flex items-center gap-2 text-lg font-semibold">
          <BadgeCheck class="h-5 w-5 text-primary" />用户等级与权益
        </h2>
        <p class="mt-1 text-sm leading-6 text-muted-foreground">
          等级治理已移入用户审批。成长值门槛需唯一且升序，首级固定为 0；保存后生成配置草稿，不直接覆盖运行时配置。
        </p>
      </div>
      <div class="flex gap-2">
        <Button type="button" variant="outline" size="sm" :disabled="loading" @click="loadLevels">
          <RefreshCw class="mr-2 h-4 w-4" />刷新
        </Button>
        <Button type="button" variant="outline" size="sm" :disabled="loading" @click="addLevel">
          <Plus class="mr-2 h-4 w-4" />新增等级
        </Button>
      </div>
    </header>

    <div v-if="error" class="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
      {{ error }}
    </div>
    <div v-if="success" class="rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm text-primary" role="status">
      {{ success }}
    </div>
    <div v-if="loading" class="py-8 text-center text-sm text-muted-foreground">正在加载用户等级配置…</div>
    <div v-else-if="levels.length === 0" class="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      尚未建立可编辑的系统配置版本。
    </div>
    <div v-else class="flex snap-x gap-4 overflow-x-auto pb-3" aria-label="用户等级横向列表" tabindex="0">
      <article
        v-for="(level, index) in levels"
        :key="`${level.code}-${index}`"
        class="w-80 shrink-0 snap-start rounded-xl border bg-background p-4 sm:w-96"
      >
        <div class="mb-4 flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <Badge variant="outline">第 {{ index + 1 }} 级</Badge>
            <span class="text-sm font-medium">{{ level.name }}</span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            :disabled="levels.length <= 1"
            :aria-label="`删除等级 ${level.name}`"
            @click="removeLevel(index)"
          >
            <Trash2 class="h-4 w-4 text-destructive" />
          </Button>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-2">
            <Label :for="`approval-level-code-${index}`">等级代码</Label>
            <Input :id="`approval-level-code-${index}`" v-model="level.code" />
          </div>
          <div class="space-y-2">
            <Label :for="`approval-level-name-${index}`">等级名称</Label>
            <Input :id="`approval-level-name-${index}`" v-model="level.name" />
          </div>
          <div class="space-y-2">
            <Label :for="`approval-level-threshold-${index}`">成长值门槛</Label>
            <Input
              :id="`approval-level-threshold-${index}`"
              v-model.number="level.min_growth_points"
              type="number"
              min="0"
              :disabled="index === 0"
            />
          </div>
          <div class="space-y-2">
            <Label :for="`approval-level-quota-${index}`">每日揭示配额</Label>
            <Input
              :id="`approval-level-quota-${index}`"
              v-model.number="level.daily_reveal_quota"
              type="number"
              min="1"
              max="1000"
            />
          </div>
          <div class="col-span-2 space-y-2">
            <Label :for="`approval-level-description-${index}`">等级说明</Label>
            <Input :id="`approval-level-description-${index}`" v-model="level.description" />
          </div>
          <div class="col-span-2 flex items-center gap-2">
            <Checkbox :id="`approval-level-submit-${index}`" v-model:checked="level.can_submit" />
            <Label :for="`approval-level-submit-${index}`">允许提交档案</Label>
          </div>
        </div>
      </article>
    </div>

    <Button v-if="levels.length > 0" type="button" :disabled="saving" @click="saveDraft">
      <Save class="mr-2 h-4 w-4" />{{ saving ? "正在保存…" : "保存为配置草稿" }}
    </Button>
  </section>
</template>
