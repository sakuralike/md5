<script setup lang="ts">
import { Copy, FileKey2, KeyRound, RotateCcw, ShieldCheck, Sparkles } from "lucide-vue-next";
import { computed, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { generateSecurePassword, type PasswordGenerationOptions } from "@/lib/passwordGenerator";
import {
  calculateLocalHash,
  DEFAULT_MAX_LOCAL_HASH_FILE_BYTES,
  LOCAL_HASH_ALGORITHMS,
  type LocalHashAlgorithm,
} from "@/services/localHash";

const selectedAlgorithm = ref<LocalHashAlgorithm>("sha256");
const textInput = ref("");
const textInputTouched = ref(false);
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const hashDigest = ref("");
const hashElapsedMs = ref<number | null>(null);
const hashProgress = ref(0);
const hashBusy = ref(false);
const hashError = ref("");
const hashNotice = ref("");
const hashAbortController = ref<AbortController | null>(null);

const passwordLength = ref(24);
const passwordOptions = ref<PasswordGenerationOptions>({
  length: 24,
  uppercase: true,
  lowercase: true,
  digits: true,
  symbols: true,
});
const generatedPassword = ref("");
const passwordError = ref("");
const passwordNotice = ref("");

const hasHashInput = computed(() => textInputTouched.value || selectedFile.value !== null);
const selectedAlgorithmLabel = computed(
  () => LOCAL_HASH_ALGORITHMS.find((item) => item.value === selectedAlgorithm.value)?.label ?? selectedAlgorithm.value,
);
const selectedCharacterTypeCount = computed(() =>
  Object.values(passwordOptions.value).filter((value) => value === true).length,
);

function onTextInput(): void {
  textInputTouched.value = true;
  if (textInput.value.length > 0) {
    selectedFile.value = null;
    if (fileInput.value) fileInput.value.value = "";
  }
  hashDigest.value = "";
  hashError.value = "";
  hashNotice.value = "";
}

function onFileSelected(event: Event): void {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  if (selectedFile.value) {
    textInput.value = "";
    textInputTouched.value = false;
  }
  hashDigest.value = "";
  hashError.value = "";
  hashNotice.value = "";
}

async function calculateHash(): Promise<void> {
  if (!hasHashInput.value) {
    hashError.value = "请输入文本或选择一个本地文件。";
    return;
  }
  hashBusy.value = true;
  hashError.value = "";
  hashNotice.value = "";
  hashDigest.value = "";
  hashProgress.value = 0;
  const controller = new AbortController();
  hashAbortController.value = controller;
  try {
    const result = await calculateLocalHash(selectedFile.value ?? textInput.value, selectedAlgorithm.value, {
      signal: controller.signal,
      maxFileSizeBytes: DEFAULT_MAX_LOCAL_HASH_FILE_BYTES,
      onProgress: (progress) => {
        hashProgress.value = progress.percent;
      },
    });
    hashDigest.value = result.digest;
    hashElapsedMs.value = result.elapsedMs;
    hashNotice.value = "摘要仅在当前浏览器页面显示，不会上传或保存历史。";
  } catch (caught) {
    hashError.value = caught instanceof DOMException && caught.name === "AbortError"
      ? "已取消本地摘要计算。"
      : caught instanceof Error
        ? caught.message
        : "本地摘要计算失败。";
  } finally {
    hashBusy.value = false;
    hashAbortController.value = null;
  }
}

function cancelHash(): void {
  hashAbortController.value?.abort();
}

async function copyHash(): Promise<void> {
  if (!hashDigest.value) return;
  try {
    await navigator.clipboard.writeText(hashDigest.value);
    hashNotice.value = "摘要已复制到剪贴板。使用后请按需清理剪贴板。";
  } catch {
    hashError.value = "当前浏览器拒绝访问剪贴板，请手动复制摘要。";
  }
}

function resetHash(): void {
  cancelHash();
  textInput.value = "";
  textInputTouched.value = false;
  selectedFile.value = null;
  if (fileInput.value) fileInput.value.value = "";
  hashDigest.value = "";
  hashElapsedMs.value = null;
  hashProgress.value = 0;
  hashError.value = "";
  hashNotice.value = "";
}

function updatePasswordLength(): void {
  passwordOptions.value.length = Number(passwordLength.value);
}

function generatePassword(): void {
  passwordError.value = "";
  passwordNotice.value = "";
  passwordOptions.value.length = Number(passwordLength.value);
  try {
    generatedPassword.value = generateSecurePassword(passwordOptions.value);
    passwordNotice.value = "密码由浏览器密码学随机源生成，不读取个人信息、历史记录或社区数据。";
  } catch (caught) {
    generatedPassword.value = "";
    passwordError.value = caught instanceof Error ? caught.message : "密码生成失败。";
  }
}

async function copyPassword(): Promise<void> {
  if (!generatedPassword.value) return;
  try {
    await navigator.clipboard.writeText(generatedPassword.value);
    passwordNotice.value = "密码已复制到剪贴板；页面不会保存生成历史。";
  } catch {
    passwordError.value = "当前浏览器拒绝访问剪贴板，请手动复制密码。";
  }
}

function resetPassword(): void {
  passwordLength.value = 24;
  passwordOptions.value = { length: 24, uppercase: true, lowercase: true, digits: true, symbols: true };
  generatedPassword.value = "";
  passwordError.value = "";
  passwordNotice.value = "";
}
</script>

<template>
  <section class="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
    <header class="space-y-4">
      <div class="flex flex-wrap items-center gap-2">
        <Badge>本地优先</Badge>
        <Badge variant="outline">不上传内容</Badge>
      </div>
      <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">本地安全工具</h1>
          <p class="mt-3 max-w-3xl text-muted-foreground">在浏览器中计算摘要或生成随机密码。输入、文件和生成结果不会发送到服务器，也不会写入历史记录。</p>
        </div>
        <div class="flex items-center gap-2 text-sm text-muted-foreground">
          <ShieldCheck class="size-4 text-primary" aria-hidden="true" />
          <span>当前页面处理</span>
        </div>
      </div>
    </header>

    <Tabs default-value="hash" class="w-full">
      <TabsList class="grid h-auto w-full grid-cols-2 sm:w-fit">
        <TabsTrigger value="hash"><FileKey2 class="mr-2 size-4" />通用哈希计算器</TabsTrigger>
        <TabsTrigger value="password"><KeyRound class="mr-2 size-4" />随机密码生成器</TabsTrigger>
      </TabsList>

      <TabsContent value="hash">
        <Card>
          <CardHeader>
            <CardTitle>通用哈希计算器</CardTitle>
            <CardDescription>支持 MD5、SHA-1、SHA-256 和 SHA-512；文本按 UTF-8 编码，文件按块读取。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-6">
            <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
              <div class="space-y-2">
                <Label for="local-hash-text">输入文本</Label>
                <Textarea id="local-hash-text" v-model="textInput" class="min-h-36 resize-y" placeholder="输入需要在本地计算摘要的文本" @input="onTextInput" />
                <p class="text-xs text-muted-foreground">保留空格和换行，页面不会记录输入内容。</p>
              </div>
              <div class="space-y-2">
                <Label for="local-hash-algorithm">摘要算法</Label>
                <Select v-model="selectedAlgorithm">
                  <SelectTrigger id="local-hash-algorithm"><SelectValue placeholder="选择算法" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="option in LOCAL_HASH_ALGORITHMS" :key="option.value" :value="option.value">{{ option.label }}</SelectItem>
                  </SelectContent>
                </Select>
                <p class="text-xs leading-5 text-muted-foreground">{{ LOCAL_HASH_ALGORITHMS.find((item) => item.value === selectedAlgorithm)?.description }}</p>
              </div>
            </div>

            <div class="rounded-lg border border-dashed p-4">
              <Label for="local-hash-file">或选择本地文件</Label>
              <Input id="local-hash-file" ref="fileInput" class="mt-2" type="file" @change="onFileSelected" />
              <p class="mt-2 text-xs text-muted-foreground">最大建议大小 2 GiB。文件只在当前浏览器内分块处理。</p>
              <p v-if="selectedFile" class="mt-2 break-all text-sm text-foreground">已选择本地文件：{{ selectedFile.name }}（{{ selectedFile.size.toLocaleString() }} bytes）</p>
            </div>

            <div class="flex flex-wrap gap-2">
              <Button type="button" :disabled="hashBusy" @click="calculateHash"><Sparkles class="size-4" />{{ hashBusy ? "计算中…" : `计算 ${selectedAlgorithmLabel}` }}</Button>
              <Button v-if="hashBusy" variant="outline" type="button" @click="cancelHash">取消</Button>
              <Button variant="outline" type="button" :disabled="hashBusy" @click="resetHash"><RotateCcw class="size-4" />重置</Button>
            </div>

            <div v-if="hashBusy || hashProgress > 0" class="space-y-2" aria-live="polite">
              <div class="flex justify-between text-xs text-muted-foreground"><span>本地处理进度</span><span>{{ hashProgress }}%</span></div>
              <Progress :model-value="hashProgress" aria-label="本地摘要计算进度" />
            </div>
            <div v-if="hashDigest" class="rounded-lg border bg-muted/30 p-4">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="text-sm font-medium">{{ selectedAlgorithmLabel }} 摘要</span>
                <Button variant="outline" size="sm" type="button" @click="copyHash"><Copy class="size-4" />复制</Button>
              </div>
              <code class="mt-3 block break-all text-sm leading-6 text-foreground">{{ hashDigest }}</code>
              <p v-if="hashElapsedMs !== null" class="mt-3 text-xs text-muted-foreground">本地计算耗时 {{ hashElapsedMs }} ms</p>
            </div>
            <p v-if="hashError" class="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ hashError }}</p>
            <p v-if="hashNotice" class="rounded-lg bg-primary/10 px-4 py-3 text-sm text-primary" role="status">{{ hashNotice }}</p>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="password">
        <Card>
          <CardHeader>
            <CardTitle>防御性随机密码生成器</CardTitle>
            <CardDescription>只使用浏览器密码学随机源，生成结果不依赖姓名、生日、用户名、历史密码或泄露数据。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-6">
            <div class="grid gap-5 sm:grid-cols-[12rem_minmax(0,1fr)]">
              <div class="space-y-2">
                <Label for="password-length">密码长度</Label>
                <Input id="password-length" v-model.number="passwordLength" type="number" min="12" max="128" step="1" @change="updatePasswordLength" />
                <p class="text-xs text-muted-foreground">12 到 128 位</p>
              </div>
              <fieldset class="space-y-3">
                <legend class="text-sm font-medium">包含字符类型</legend>
                <div class="grid gap-3 sm:grid-cols-2">
                  <label class="flex items-center gap-2 text-sm"><Checkbox v-model="passwordOptions.uppercase" /><span>大写字母</span></label>
                  <label class="flex items-center gap-2 text-sm"><Checkbox v-model="passwordOptions.lowercase" /><span>小写字母</span></label>
                  <label class="flex items-center gap-2 text-sm"><Checkbox v-model="passwordOptions.digits" /><span>数字</span></label>
                  <label class="flex items-center gap-2 text-sm"><Checkbox v-model="passwordOptions.symbols" /><span>符号</span></label>
                </div>
                <p class="text-xs text-muted-foreground">已选择 {{ selectedCharacterTypeCount }} 类字符；每一类都会至少出现一次。</p>
              </fieldset>
            </div>

            <div class="flex flex-wrap gap-2">
              <Button type="button" @click="generatePassword"><KeyRound class="size-4" />生成随机密码</Button>
              <Button variant="outline" type="button" :disabled="!generatedPassword" @click="copyPassword"><Copy class="size-4" />复制结果</Button>
              <Button variant="outline" type="button" @click="resetPassword"><RotateCcw class="size-4" />重置</Button>
            </div>

            <div v-if="generatedPassword" class="rounded-lg border bg-muted/30 p-4" aria-live="polite">
              <span class="text-sm font-medium">本次生成结果</span>
              <code class="mt-3 block break-all rounded-md bg-background px-3 py-3 text-base tracking-wide text-foreground">{{ generatedPassword }}</code>
            </div>
            <p v-if="passwordError" class="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ passwordError }}</p>
            <p v-if="passwordNotice" class="rounded-lg bg-primary/10 px-4 py-3 text-sm text-primary" role="status">{{ passwordNotice }}</p>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  </section>
</template>
