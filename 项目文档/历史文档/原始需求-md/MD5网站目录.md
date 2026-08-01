# MD5网站目录

> 状态：历史需求参考，不作为当前开发基线。若与 v3.0 规格冲突，以当前规格说明书为准。

> 原始来源：`MD5网站目录.docx`

```text
password-detective/
├── backend/ # 后端服务根目录 (FastAPI)
│ ├── app/ # 应用程序主目录
│ │ ├── api/ # API 接口层
│ │ │ ├── v1/ # API 版本 v1
│ │ │ │ ├── endpoints/ # 各功能模块的端点
│ │ │ │ │ ├── __init__.py
│ │ │ │ │ ├── auth.py # 用户认证 (登录/注册/Token刷新)
│ │ │ │ │ ├── users.py # 用户信息 (个人资料/积分/信誉分)
│ │ │ │ │ ├── search.py # 哈希查询 (hash-to-plain/plain-to-hash)
│ │ │ │ │ ├── submission.py # 数据提交 (用户提交哈希-明文对)
│ │ │ │ │ ├── community.py # 社区功能 (评论/论坛/悬赏)
│ │ │ │ │ ├── rewards.py # 积分商城 (商品/订单/兑换)
│ │ │ │ │ └── admin/ # 后台管理接口
│ │ │ │ │ ├── __init__.py
│ │ │ │ │ ├── dashboard.py # 仪表盘数据
│ │ │ │ │ ├── data_manage.py # 数据管理 (CRUD/审核/批量操作)
│ │ │ │ │ ├── user_manage.py # 用户管理 (封禁/积分修改/日志)
│ │ │ │ │ ├── crawler_manage.py # 爬虫管理 (任务/日志/配置)
│ │ │ │ │ ├── system_monitor.py # 系统监控 (API/服务器/告警)
│ │ │ │ │ ├── content_manage.py # 内容运营 (评论/论坛/商城/公告)
│ │ │ │ │ └── operation_log.py # 操作审计日志
│ │ │ │ ├── __init__.py
│ │ │ │ └── deps.py # 依赖注入 (数据库会话/当前用户/权限检查)
│ │ │ └── __init__.py
│ │ ├── core/ # 核心配置与工具
│ │ │ ├── __init__.py
│ │ │ ├── config.py # 全局配置 (数据库/Redis/JWT/爬虫设置)
│ │ │ ├── security.py # 安全工具 (密码哈希/JWT生成与验证/2FA)
│ │ │ ├── exceptions.py # 自定义异常处理
│ │ │ └── permissions.py # RBAC权限控制函数
│ │ ├── models/ # SQLAlchemy ORM 模型
│ │ │ ├── __init__.py
│ │ │ ├── hash_record.py # 哈希记录模型
│ │ │ ├── user.py # 用户模型
│ │ │ ├── contribution_log.py # 贡献日志模型
│ │ │ ├── comment.py # 评论模型
│ │ │ ├── forum_post.py # 论坛帖子模型
│ │ │ ├── bounty_task.py # 悬赏任务模型
│ │ │ ├── shop_item.py # 积分商品模型
│ │ │ ├── order.py # 订单模型
│ │ │ ├── admin_user.py # 管理员用户模型
│ │ │ ├── operation_log.py # 操作审计日志模型
│ │ │ ├── crawler_task.py # 爬虫任务模型
│ │ │ └── system_alert.py # 系统告警规则模型
│ │ ├── schemas/ # Pydantic 数据验证模型 (请求/响应)
│ │ │ ├── __init__.py
│ │ │ ├── auth.py # 登录/注册请求体
│ │ │ ├── user.py # 用户信息响应体
│ │ │ ├── hash_record.py # 哈希记录请求/响应体
│ │ │ ├── search.py # 搜索请求/响应体
│ │ │ ├── submission.py # 提交请求/响应体
│ │ │ ├── community.py # 社区相关请求/响应体
│ │ │ ├── rewards.py # 商城相关请求/响应体
│ │ │ └── admin/ # 后台管理请求/响应体
│ │ │ ├── __init__.py
│ │ │ ├── dashboard.py
│ │ │ ├── data_manage.py
│ │ │ ├── user_manage.py
│ │ │ ├── crawler_manage.py
│ │ │ ├── system_monitor.py
│ │ │ ├── content_manage.py
│ │ │ └── operation_log.py
│ │ ├── services/ # 业务逻辑层
│ │ │ ├── __init__.py
│ │ │ ├── auth_service.py # 认证服务
│ │ │ ├── user_service.py # 用户服务
│ │ │ ├── search_service.py # 查询服务 (核心算法)
│ │ │ ├── submission_service.py # 提交服务 (数据验证/积分发放)
│ │ │ ├── community_service.py # 社区服务
│ │ │ ├── rewards_service.py # 积分商城服务
│ │ │ ├── data_manage_service.py # 后台数据管理服务
│ │ │ ├── crawler_service.py # 爬虫管理服务
│ │ │ ├── monitor_service.py # 监控与告警服务
│ │ │ └── operation_log_service.py # 操作日志服务
│ │ ├── tasks/ # 异步任务 (Celery)
│ │ │ ├── __init__.py
│ │ │ ├── celery_app.py # Celery 应用实例
│ │ │ ├── crawler_tasks.py # 爬虫定时任务
│ │ │ ├── data_cleanup.py # 数据清理任务
│ │ │ └── notification.py # 通知发送任务
│ │ ├── utils/ # 工具函数
│ │ │ ├── __init__.py
│ │ │ ├── hash_utils.py # 哈希计算工具
│ │ │ ├── rate_limiter.py # 限流器 (基于Redis)
│ │ │ └── validators.py # 自定义验证器
│ │ └── main.py # FastAPI 应用入口
│ ├── tests/ # 单元测试与集成测试
│ │ ├── __init__.py
│ │ ├── test_api/
│ │ │ ├── test_auth.py
│ │ │ ├── test_search.py
│ │ │ └── test_submission.py
│ │ ├── test_services/
│ │ │ ├── test_search_service.py
│ │ │ └── test_submission_service.py
│ │ └── conftest.py # pytest 配置文件
│ ├── alembic/ # 数据库迁移 (Alembic)
│ │ ├── versions/
│ │ ├── env.py
│ │ └── alembic.ini
│ ├── crawlers/ # 爬虫脚本 (独立运行或Celery调用)
│ │ ├── __init__.py
│ │ ├── base_crawler.py # 爬虫基类
│ │ ├── seclists_crawler.py # SecLists 数据源爬虫
│ │ ├── probable_wordlists_crawler.py # Probable Wordlists 爬虫
│ │ └── utils.py # 爬虫工具 (请求/解析/去重)
│ ├── requirements.txt # Python 依赖
│ ├── Dockerfile # 后端 Docker 镜像
│ └── .env.example # 环境变量示例
│
├── frontend/ # 前台用户端 (Vue3)
│ ├── public/
│ │ ├── favicon.ico
│ │ └── index.html
│ ├── src/
│ │ ├── api/ # API 请求封装
│ │ │ ├── index.js # Axios 实例与拦截器
│ │ │ ├── auth.js
│ │ │ ├── search.js
│ │ │ ├── submission.js
│ │ │ ├── community.js
│ │ │ └── rewards.js
│ │ ├── assets/ # 静态资源 (图片/样式)
│ │ │ ├── styles/
│ │ │ │ ├── main.scss
│ │ │ │ └── variables.scss
│ │ │ └── images/
│ │ ├── components/ # 通用组件
│ │ │ ├── Header.vue
│ │ │ ├── Footer.vue
│ │ │ ├── HashSearch.vue
│ │ │ └── ResultCard.vue
│ │ ├── layouts/ # 布局组件
│ │ │ ├── DefaultLayout.vue
│ │ │ └── AuthLayout.vue
│ │ ├── router/ # 路由配置
│ │ │ └── index.js
│ │ ├── store/ # 状态管理 (Pinia)
│ │ │ ├── index.js
│ │ │ ├── user.js
│ │ │ └── app.js
│ │ ├── views/ # 页面视图
│ │ │ ├── Home.vue
│ │ │ ├── Login.vue
│ │ │ ├── Register.vue
│ │ │ ├── Dashboard.vue # 用户个人中心
│ │ │ ├── Search.vue
│ │ │ ├── Submit.vue
│ │ │ ├── Community.vue
│ │ │ ├── Bounty.vue
│ │ │ └── Shop.vue
│ │ ├── App.vue
│ │ └── main.js
│ ├── Dockerfile
│ ├── nginx.conf # 前台 Nginx 配置
│ └── package.json
│
├── admin-frontend/ # 后台管理端 (Vue3)
│ ├── public/
│ │ ├── favicon.ico
│ │ └── index.html
│ ├── src/
│ │ ├── api/ # 后台 API 请求封装
│ │ │ ├── index.js
│ │ │ ├── dashboard.js
│ │ │ ├── dataManage.js
│ │ │ ├── userManage.js
│ │ │ ├── crawlerManage.js
│ │ │ ├── systemMonitor.js
│ │ │ └── contentManage.js
│ │ ├── assets/
│ │ │ ├── styles/
│ │ │ │ ├── admin.scss
│ │ │ │ └── variables.scss
│ │ │ └── images/
│ │ ├── components/ # 后台通用组件
│ │ │ ├── Sidebar.vue
│ │ │ ├── Navbar.vue
│ │ │ ├── DataTable.vue # 通用数据表格
│ │ │ └── SearchForm.vue # 通用搜索表单
│ │ ├── layouts/
│ │ │ └── AdminLayout.vue
│ │ ├── router/
│ │ │ └── index.js
│ │ ├── store/
│ │ │ ├── index.js
│ │ │ └── admin.js
│ │ ├── views/ # 后台页面视图
│ │ │ ├── Login.vue
│ │ │ ├── Dashboard.vue
│ │ │ ├── data/
│ │ │ │ ├── HashRecords.vue
│ │ │ │ └── PendingReview.vue
│ │ │ ├── users/
│ │ │ │ ├── UserList.vue
│ │ │ │ └── UserDetail.vue
│ │ │ ├── crawlers/
│ │ │ │ ├── TaskList.vue
│ │ │ │ └── TaskLog.vue
│ │ │ ├── monitor/
│ │ │ │ ├── ApiMonitor.vue
│ │ │ │ ├── ServerMonitor.vue
│ │ │ │ └── AlertConfig.vue
│ │ │ ├── content/
│ │ │ │ ├── Comments.vue
│ │ │ │ ├── Forum.vue
│ │ │ │ ├── BountyTasks.vue
│ │ │ │ ├── ShopItems.vue
│ │ │ │ └── Orders.vue
│ │ │ └── system/
│ │ │ ├── AdminUsers.vue
│ │ │ └── OperationLogs.vue
│ │ ├── App.vue
│ │ └── main.js
│ ├── Dockerfile
│ ├── nginx.conf # 后台 Nginx 配置
│ └── package.json
│
├── nginx/ # 反向代理配置
│ ├── nginx.conf # 主 Nginx 配置 (路由前台/后台/API)
│ └── conf.d/
│ └── default.conf
│
├── scripts/ # 部署与运维脚本
│ ├── init_db.sql # 数据库初始化 SQL
│ ├── seed_data.py # 种子数据填充脚本
│ └── deploy.sh # 一键部署脚本 (Docker Compose)
│
├── docker-compose.yml # 多服务编排 (MySQL/Redis/Backend/Frontend/Admin/Celery)
├── .gitignore
├── README.md # 项目说明文档
└── CHANGELOG.md # 版本更新日志
```

## 目录结构说明

## 表 1

| 目录/文件 | 功能描述 |
| --- | --- |
| backend/ | FastAPI 后端服务，包含API、模型、服务、任务、爬虫等。 |
| frontend/ | 用户端 Vue3 前端项目，面向普通用户。 |
| admin-frontend/ | 管理端 Vue3 前端项目，面向管理员，独立部署。 |
| nginx/ | 反向代理配置，统一路由前台、后台和API请求。 |
| scripts/ | 数据库初始化、数据填充、一键部署等运维脚本。 |
| docker-compose.yml | 定义所有服务（MySQL、Redis、后端、前端、后台、Celery Worker/Beat）的编排。 |
