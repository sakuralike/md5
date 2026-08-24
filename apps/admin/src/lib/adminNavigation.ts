import {
  BellRing,
  ClipboardList,
  Database,
  FileCheck2,
  Flag,
  History,
  KeyRound,
  LayoutDashboard,
  MonitorUp,
  Megaphone,
  ShoppingBag,
  Settings2,
  ShieldAlert,
  SlidersHorizontal,
  UsersRound,
  UserRoundCog,
  type LucideIcon,
} from "lucide-vue-next";

export interface AdminNavigationItem {
  label: string;
  path: string;
  description: string;
  group: "内容治理" | "安全运营" | "系统管理";
  icon: LucideIcon;
}

export const dashboardNavigationItem: AdminNavigationItem = {
  label: "仪表盘",
  path: "/",
  description: "查看安全运营指标、待办队列与全部管理功能站内路径。",
  group: "安全运营",
  icon: LayoutDashboard,
};

export const adminSettingsNavigationItems: readonly AdminNavigationItem[] = [
  {
    label: "候选审核",
    path: "/candidates",
    description: "审核候选证据并执行状态处置。",
    group: "内容治理",
    icon: FileCheck2,
  },
  {
    label: "总哈希池",
    path: "/hash-pool",
    description: "检索已验证候选及其存档哈希与证据摘要。",
    group: "内容治理",
    icon: Database,
  },
  {
    label: "举报申诉",
    path: "/trust-cases",
    description: "处理举报、申诉与信任案件。",
    group: "内容治理",
    icon: Flag,
  },
  {
    label: "社区治理",
    path: "/community",
    description: "审核社区主题、评论与治理事件。",
    group: "内容治理",
    icon: UsersRound,
  },
  {
    label: "社区配置",
    path: "/community/settings",
    description: "配置社区板块、权限与生命周期。",
    group: "内容治理",
    icon: SlidersHorizontal,
  },
  {
    label: "通知运维",
    path: "/community/notifications",
    description: "查询社区通知 Outbox 失败并执行受控重放。",
    group: "安全运营",
    icon: BellRing,
  },
  {
    label: "搜索健康",
    path: "/community/search-health",
    description: "查看社区搜索 Provider、索引 Outbox 与重建的聚合健康状态。",
    group: "安全运营",
    icon: Database,
  },
  {
    label: "数据热度",
    path: "/analytics/heatmap",
    description: "查看按日期、星期和社区板块聚合的隐私热度区间。",
    group: "安全运营",
    icon: Database,
  },
  {
    label: "风险告警",
    path: "/risk-alerts",
    description: "处置风险告警、分派与通知回放。",
    group: "安全运营",
    icon: ShieldAlert,
  },
  {
    label: "第三方 API",
    path: "/third-party-apps",
    description: "审核第三方桌面应用、权限范围与可信验证能力。",
    group: "安全运营",
    icon: KeyRound,
  },
  {
    label: "桌面发布",
    path: "/desktop-releases",
    description: "管理桌面端制品、发布与撤回。",
    group: "安全运营",
    icon: MonitorUp,
  },
  {
    label: "桌面公告",
    path: "/desktop-announcements",
    description: "管理桌面端公告、图片轮播与投放时间窗。",
    group: "安全运营",
    icon: Megaphone,
  },
  {
    label: "Web 公告",
    path: "/web-announcements",
    description: "独立管理网站右下角弹窗公告与自动关闭时间。",
    group: "安全运营",
    icon: Megaphone,
  },
  {
    label: "审计日志",
    path: "/audit",
    description: "筛选、查看并导出受控审计记录。",
    group: "安全运营",
    icon: History,
  },
  {
    label: "用户审批",
    path: "/users",
    description: "按用户名、邮箱或 UID 查找并治理账号。",
    group: "系统管理",
    icon: UserRoundCog,
  },
  {
    label: "邀请码与邀请链接",
    path: "/registration",
    description: "管理邀请码注册策略与用户邀请链接开关。",
    group: "系统管理",
    icon: KeyRound,
  },
  {
    label: "角色审批",
    path: "/role-changes",
    description: "管理角色变更请求与审批记录。",
    group: "系统管理",
    icon: BellRing,
  },
  {
    label: "系统配置",
    path: "/settings",
    description: "配置站点、邮件、策略与发布门禁。",
    group: "系统管理",
    icon: Settings2,
  },
  {
    label: "积分商城",
    path: "/rewards/catalog",
    description: "治理虚拟积分商品目录、价格、库存和上架状态。",
    group: "系统管理",
    icon: ShoppingBag,
  },
  {
    label: "商城订单",
    path: "/rewards/orders",
    description: "查看积分兑换订单、履约状态、补偿与运营指标。",
    group: "系统管理",
    icon: ClipboardList,
  },
];

export const allAdminNavigationItems: readonly AdminNavigationItem[] = [
  dashboardNavigationItem,
  ...adminSettingsNavigationItems,
];

export const adminNavigationGroups = ["内容治理", "安全运营", "系统管理"] as const;
