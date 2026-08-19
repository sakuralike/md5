export type SearchSuggestionKind = "algorithm" | "board" | "filter" | "navigation";

export interface SearchSuggestion {
  id: string;
  label: string;
  value: string;
  description: string;
  kind: SearchSuggestionKind;
}

const PUBLIC_SUGGESTIONS: readonly SearchSuggestion[] = [
  { id: "algorithm-md5", label: "MD5", value: "MD5", description: "公开算法名称", kind: "algorithm" },
  { id: "algorithm-sha1", label: "SHA-1", value: "SHA-1", description: "公开算法名称", kind: "algorithm" },
  { id: "algorithm-sha256", label: "SHA-256", value: "SHA-256", description: "公开算法名称", kind: "algorithm" },
  { id: "algorithm-sha512", label: "SHA-512", value: "SHA-512", description: "公开算法名称", kind: "algorithm" },
  { id: "board-general", label: "社区广场", value: "社区广场", description: "公开社区板块", kind: "board" },
  { id: "board-recovery", label: "恢复指南", value: "恢复指南", description: "公开社区板块", kind: "board" },
  { id: "board-verification", label: "验证协作", value: "验证协作", description: "公开社区板块", kind: "board" },
  { id: "board-security", label: "安全与隐私", value: "安全与隐私", description: "公开社区板块", kind: "board" },
  { id: "filter-post", label: "主题", value: "主题", description: "公开内容筛选项", kind: "filter" },
  { id: "filter-user", label: "用户", value: "用户", description: "公开内容筛选项", kind: "filter" },
  { id: "filter-board", label: "板块", value: "板块", description: "公开内容筛选项", kind: "filter" },
  { id: "filter-group", label: "群组", value: "群组", description: "公开内容筛选项", kind: "filter" },
  { id: "nav-community", label: "社区", value: "社区", description: "公开导航入口", kind: "navigation" },
  { id: "nav-tools", label: "本地安全工具", value: "本地安全工具", description: "公开导航入口", kind: "navigation" },
];

export function getPublicSearchSuggestions(query: string, limit = 6): SearchSuggestion[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized || isDisallowedSuggestionQuery(normalized)) return [];
  return PUBLIC_SUGGESTIONS
    .filter((suggestion) => suggestion.label.toLocaleLowerCase().includes(normalized))
    .slice(0, Math.max(0, limit));
}

export function isDisallowedSuggestionQuery(query: string): boolean {
  return query.length > 72
    || /[\\/]/.test(query)
    || /^[0-9a-f]{8,}$/i.test(query)
    || /(密码|明文|候选|password|passwd|secret|token)/i.test(query);
}
