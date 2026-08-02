<template>
  <section class="stack">
    <div class="panel">
      <div class="eyebrow">安全运营工作台</div>
      <h1>管理端</h1>
      <p class="lead">当前已完成独立入口、角色路由、TOTP 门禁、桌面版本受控发布和候选人工审核闭环。举报处置、配置与指标将在 M4 后续切片接入。</p>
    </div>
    <div class="grid">
      <RouterLink class="card dashboard-link" to="/desktop-releases">
        <span class="badge">M3 已接入</span><h2>桌面版本发布</h2><p class="muted">创建发布草稿、上传制品、复核摘要与签名记录，并执行发布或撤回。</p>
      </RouterLink>
      <RouterLink class="card dashboard-link" to="/candidates"><span class="badge">M4 已接入</span><h2>候选审核</h2><p class="muted">按状态与指纹筛选候选，查看证据时间线并执行具备幂等和审计约束的状态处置。</p></RouterLink>
      <article class="card"><span class="badge">待接入</span><h2>风险告警</h2><p class="muted">展示失败激增、刷票关联和异常揭示。</p></article>
      <article class="card"><span class="badge">基础已建</span><h2>审计</h2><p class="muted">认证和桌面发布事件已写入审计表，查询 API 在后续切片开放。</p></article>
    </div>
  </section>
</template>

<style scoped>
.dashboard-link { color: inherit; text-decoration: none; transition: transform .18s ease, box-shadow .18s ease; }
.dashboard-link:hover { transform: translateY(-2px); box-shadow: 0 14px 30px rgba(23, 32, 51, .08); }
</style>
