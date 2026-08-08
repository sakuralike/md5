#!/usr/bin/env node

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const baselinePath = path.join(root, "scripts", "frontend-policy-baseline.json");
const scanRoots = [path.join(root, "apps", "web", "src"), path.join(root, "apps", "admin", "src")];
const rules = [
  { id: "style-block", pattern: /<style(?:\s[^>]*)?>/g, message: "业务 Vue 文件不得包含 <style> 块" },
  { id: "inline-style", pattern: /\s(?::|v-bind:)?style\s*=/g, message: "业务 Vue 文件不得包含行内 style 绑定" },
  { id: "hex-color", pattern: /#[0-9A-Fa-f]{3,8}\b/g, message: "业务 Vue 文件不得包含硬编码十六进制颜色" },
  { id: "native-button", pattern: /<button\b/g, message: "请使用 Shadcn-Vue Button" },
  { id: "native-input", pattern: /<input\b/g, message: "请使用 Shadcn-Vue Input 或 Checkbox" },
  { id: "native-select", pattern: /<select\b/g, message: "请使用 Shadcn-Vue Select" },
  { id: "native-textarea", pattern: /<textarea\b/g, message: "请使用 Shadcn-Vue Textarea" },
];

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (target.includes(`${path.sep}components${path.sep}ui`)) continue;
      files.push(...await walk(target));
    } else if (entry.isFile() && entry.name.endsWith(".vue")) {
      files.push(target);
    }
  }
  return files;
}

function lineOf(source, index) {
  return source.slice(0, index).split("\n").length;
}

const baseline = JSON.parse(await readFile(baselinePath, "utf8"));
const violations = [];
const counts = {};
for (const scanRoot of scanRoots) {
  for (const file of await walk(scanRoot)) {
    const source = await readFile(file, "utf8");
    const relative = path.relative(root, file).replaceAll(path.sep, "/");
    counts[relative] = {};
    for (const rule of rules) {
      const matches = [...source.matchAll(rule.pattern)];
      counts[relative][rule.id] = matches.length;
      const allowed = baseline[relative]?.[rule.id] ?? 0;
      if (matches.length <= allowed) continue;
      for (const match of matches.slice(allowed)) {
        violations.push(`${relative}:${lineOf(source, match.index ?? 0)} [${rule.id}] ${rule.message}`);
      }
    }
  }
}

const staleBaseline = [];
for (const [file, allowances] of Object.entries(baseline)) {
  for (const [ruleId, allowed] of Object.entries(allowances)) {
    const actual = counts[file]?.[ruleId] ?? 0;
    if (actual < allowed) staleBaseline.push(`${file} [${ruleId}] baseline=${allowed}, actual=${actual}`);
  }
}

if (violations.length) {
  console.error("前端规范门禁失败：\n" + violations.join("\n"));
  process.exit(1);
}
if (staleBaseline.length) {
  console.error("前端规范基线已减少，请同步收紧 scripts/frontend-policy-baseline.json：\n" + staleBaseline.join("\n"));
  process.exit(1);
}
const debtCount = Object.values(baseline).reduce(
  (total, allowances) => total + Object.values(allowances).reduce((sum, value) => sum + value, 0),
  0,
);
console.log(`前端规范门禁通过；当前冻结 ${debtCount} 项历史欠账，新增违规为 0。`);
