# 数据库迁移

迁移事实来源位于 `apps/api/alembic/`。执行：

```powershell
Set-Location apps/api
./.venv/Scripts/alembic upgrade head
```

生产变更遵循“先兼容、再切换、后清理”，每次迁移必须在发布说明中包含回滚或前向修复策略。
