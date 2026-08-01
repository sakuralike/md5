# MD5

> 状态：历史需求参考，不作为当前开发基线。若与 v3.0 规格冲突，以当前规格说明书为准。

> 原始来源：`MD5.docx`

## 项目概述

- 目标：构建一个支持多算法（MD5/SHA1/SHA256/SHA512）的密码明文查询平台，提供本地验证工具，允许用户贡献与积分激励。

- 核心功能：

- 正向查询（哈希值→明文）

- 反向查询（明文→哈希值）

- 贡献密码（网页端进入待验证池，桌面端标记为初步验证）

- 积分/等级系统

- 热门密码排行榜

- 桌面端加密压缩包解密与验证

#### 技术栈

API 网关 Nginx + OpenResty

后端 - 核心业务 PHP + Laravel

后端 - 爬虫 AI Python+FastAPI/Django

后端 - 高性能查询 Go + Gin/Echo

桌面端 C# +WPF

数据库 MySQL (主从)

#### 数据库设计

#### 1hash_records表（主表）

CREATETABLEhash_records(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

hash_typeENUM('MD5','SHA1','SHA256','SHA512')NOTNULL,

hash_valueCHAR(128)NOTNULL,--定长，MD5=32，SHA1=40，SHA256=64，SHA512=128

plaintextVARCHAR(1024)NOTNULL,

submitter_idINTNOTNULL,--关联users.id

sourceENUM('web','desktop')NOTNULLDEFAULT'web',--提交来源

statusENUM('pending','preliminary','verified','rejected')NOTNULLDEFAULT'pending',

verify_countINTDEFAULT0,--查询命中次数

confirm_countINTDEFAULT0,--社区确认次数

submit_timeDATETIMEDEFAULTCURRENT_TIMESTAMP,

verified_timeDATETIMENULL,

INDEXidx_type_value(hash_type,hash_value),

INDEXidx_submitter(submitter_id),

INDEXidx_status(status)

)ENGINE=InnoDBDEFAULTCHARSET=utf8mb4;

分区建议：按hash_type分区（4个分区），提升查询效率。

#### 1hash_records表（修改版）

CREATETABLEhash_records(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

hash_typeENUM('MD5','SHA1','SHA256','SHA512')NOTNULL,

hash_valueCHAR(128)NOTNULL,

plaintextVARCHAR(1024)NOTNULL,

submitter_idINTNOTNULL,--用户提交时记录用户ID，公开爬取时固定为系统用户ID（如0或-1）

sourceENUM('web','desktop','crawl')NOTNULLDEFAULT'web',--提交来源：web/desktop/crawl

source_typeENUM('user','public_crawl')NOTNULLDEFAULT'user',--数据来源类型：用户提交/公开爬取

statusENUM('pending','preliminary','verified','rejected')NOTNULLDEFAULT'pending',

verify_countINTDEFAULT0,

confirm_countINTDEFAULT0,

filenamesTEXTNULL,--压缩包内文件名（仅桌面端提交时携带）

submit_timeDATETIMEDEFAULTCURRENT_TIMESTAMP,

verified_timeDATETIMENULL,

INDEXidx_type_value(hash_type,hash_value),

INDEXidx_submitter(submitter_id),

INDEXidx_status(status),

INDEXidx_source_type(source_type)

)ENGINE=InnoDBDEFAULTCHARSET=utf8mb4;

说明：

source='crawl'表示该数据由后台爬虫自动入库。

source_type='public_crawl'明确标记为公开爬取数据，区别于用户贡献数据（source_type='user'）。

公开爬取数据的submitter_id固定为系统预留用户ID（如0或-1），不参与积分计算。

公开爬取数据的status直接设为verified（无需社区验证），因为来源可靠。

#### users表

CREATETABLEusers(

idINTAUTO_INCREMENTPRIMARYKEY,

usernameVARCHAR(50)UNIQUENOTNULL,

password_hashVARCHAR(256)NOTNULL,--bcrypt加密

pointsINTDEFAULT0,--总积分

levelTINYINTDEFAULT1,--等级（1-10）

daily_queriesINTDEFAULT10,--每日剩余查询次数

last_query_dateDATE,--最近查询日期

reputationINTDEFAULT100,--信誉分

created_atDATETIMEDEFAULTCURRENT_TIMESTAMP

);

等级对应每日查询次数：

- 等级1：10次/天

- 等级2：20次/天

- 每升一级+10次，最高等级10级=100次/天

#### contribution_log表

CREATETABLEcontribution_log(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

user_idINTNOTNULL,

hash_typeENUM('MD5','SHA1','SHA256','SHA512')NOTNULL,

hash_valueCHAR(128)NOTNULL,

plaintextVARCHAR(1024)NOTNULL,

sourceENUM('web','desktop')NOTNULLDEFAULT'web',

statusENUM('pending','preliminary','verified','rejected')NOTNULLDEFAULT'pending',

earned_pointsINTDEFAULT0,--实际获得积分

submit_timeDATETIMEDEFAULTCURRENT_TIMESTAMP

);

#### API接口清单

#### 公共接口

#### 用户认证接口

#### 贡献与验证接口

#### 桌面端专用接口

#### 接口参数示例

正向查询：

GET/api/search/hash-to-plain?hash_type=MD5&hash_value=482c811da5d5b4bc6d497ffa98491e38

响应：

on

{

"success":true,

"data":{

"plaintext":"password123",

"verify_count":5,

"status":"verified"

}

}

反向查询：

GET/api/search/plain-to-hash?plaintext=password123

响应：

on

{

"success":true,

"data":[

{"hash_type":"MD5","hash_value":"482c811da5d5b4bc6d497ffa98491e38"},

{"hash_type":"SHA1","hash_value":"5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8"},

{"hash_type":"SHA256","hash_value":"5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"},

{"hash_type":"SHA512","hash_value":"b109f3bbbc244eb82441917ed06d618b9008dd09b3befd1b5e073548ab1f94a8e20a9f0a1f5c4f3e7b1c5f4e3d2c1a"}

]

}

#### 贡献与积分机制

#### 提交来源与初始状态

- 网页端提交：用户通过浏览器提交，数据库source='web'，初始状态status='pending'。

- 桌面端提交：用户通过C#桌面端提交，请求头携带User-Agent:DeepPwdDesktop/2.x等程序标识，后端验证通过后，初始状态status='preliminary'，source='desktop'。若未通过标识验证，则降级为pending。

#### 验证晋级条件（组合方案A+B）

满足以下任一条件，数据变为verified，提交者获得积分：

#### 社区确认数≥3（方案A）

- 每个用户对同一条数据只能确认一次。

- 确认者等级必须≥3。

#### 查询命中次数≥10（方案B）

- 其他用户正向查询该哈希并返回结果时，verify_count自增。

计时：提交后7天内未满足条件，自动变为rejected，不发放积分。

#### 积分规则

积分在数据变为verified时一次性发放。

#### 信誉分机制

- 每个用户初始信誉分100。

- 每次提交被驳回（rejected）：信誉分-10。

- 每次提交成功验证（verified）：信誉分+5。

- 信誉分<60：暂停提交功能，需联系管理员手动恢复。

#### 前端界面设计（二次元风格）

#### 首页布局

+---------------------------------------------------------------------+

|[登录按钮]🕵️‍♂️密码侦探社(LOGO)|

|(右上角)|

|+-----------------------------------------------------------------+|

||🔍正向查询📖反向查询(模式切换tab)||

||[输入框_________________________________][查询]||

||||

||热门排行榜(下方)||

||🥇123456(SHA256)1000次||

||🥈password900次||

||🥉qwerty800次||

|+-------------------------------------------------------------------+|

|背景:渐变星空+漂浮云朵+Q版角色剪影|

+---------------------------------------------------------------------+

#### 关键组件

- 登录按钮：左上角，毛玻璃效果，图标使用FontAwesomefa-user-astronaut。

- LOGO：右上角，猫爪图标+“密码侦探社”文字，渐变紫粉色。

- 模式切换：两个标签（正向/反向），圆角胶囊样式，激活态渐变。

- 查询输入框：磨砂玻璃效果，霓虹边框，占位符根据模式自动变化。

- 查询按钮：紫粉渐变，悬停上浮发光。

- 排行榜卡片：半透明毛玻璃，金色/银色/铜色奖杯图标。

#### 配色方案

#### 验证与状态流转图

+-----------+

|提交|

+-----------+

|

+------------+-------------+

||

网页端提交桌面端提交

||

source='web'source='desktop'

||

status='pending'status='preliminary'

||

+----------+---------------+

|

组合验证（A或B条件）

|

+----------+-----------+

||

社区确认≥3查询命中≥10

|或|

+----------+-----------+

|

变为verified

|

积分发放

#### 安全与风险控制

- API限流：基于Redis的滑动窗口实现，防止爬虫。

- SQL注入：所有查询参数化。

- 用户密码：bcrypt加密，JWT带黑名单。

- 哈希校验：提交时后端验证SHA256(plaintext)==hash_value，防止无效数据。

- 数据展示：对已泄露密码，前端默认只显示前2后2字符，鼠标悬浮可查看完整（需额外点击确认）。

#### 后续扩展计划

#### 桌面端提交携带文件名信息

功能描述：

- 桌面端在通过加密压缩包解压验证后，提交数据时，除了明文（密码）和哈希值外，还需携带压缩包内包含的文件名列表（如readme.txt,secret.png）。

- 网页端查询哈希值时，若该数据来自桌面端且携带了文件名，则显示“压缩包内文件：”字样及文件列表。

数据表修改：在hash_records表中增加字段：

ALTERTABLEhash_recordsADDCOLUMNfilenamesTEXTNULLCOMMENT'压缩包内文件名列表，逗号分隔';

API接口调整：

- 桌面端提交接口/api/tool/submit增加可选参数filenames（字符串，逗号分隔）。

- 正向查询接口/api/search/hash-to-plain响应中增加filenames字段。

前端展示：在查询结果卡片中增加一行：

压缩包内文件：readme.txt,secret.png

若无文件名，则不显示。

#### 悬赏大厅功能

功能描述：

- 登录用户可以发布悬赏任务：输入一个哈希值（及算法类型），设置悬赏积分（从用户积分中扣除并暂时冻结）。

- 其他用户可以在悬赏大厅中看到所有未关闭的悬赏任务，并尝试提交密码。

- 发布者收到密码后，手动验证（可在网页端输入密码并计算哈希比对），若正确则点击“确认正确”，系统将从冻结积分中扣除悬赏积分，奖励给提供者。若发布者未在指定时间内（如7天）确认，系统自动退还积分。

- 悬赏任务状态：open（开放）、locked（已有人提交待验证）、completed（已完成）、expired（过期）。

数据库新增表：

CREATETABLEbounty(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

publisher_idINTNOTNULL,--发布者用户ID

hash_typeENUM('MD5','SHA1','SHA256','SHA512')NOTNULL,

hash_valueCHAR(128)NOTNULL,

reward_pointsINTNOTNULL,--悬赏积分

statusENUM('open','locked','completed','expired')NOTNULLDEFAULT'open',

solver_idINTNULL,--提供者用户ID

solved_timeDATETIMENULL,

expire_timeDATETIMENOTNULL,--过期时间

created_atDATETIMEDEFAULTCURRENT_TIMESTAMP

);

API 新增接口：

前端页面：

- 悬赏大厅页面：展示所有未完成的悬赏，按时间倒序，每条显示哈希值（截断）、算法、悬赏积分、剩余时间、状态。

- 点击任务进入详情：输入密码提交。

- 发布者个人中心可以查看自己发布的悬赏状态。

积分冻结与释放：

- 发布任务时，立即从用户积分扣除reward_points，并记入frozen_points字段。

- 任务完成后，frozen_points减少，同时提供者增加积分。

- 任务取消或过期，积分退回发布者。

#### 积分商城

功能描述：

- 用户可以使用积分兑换各种虚拟或实物奖励。

- 虚拟奖励：API调用次数加成、VIP身份标识（金色头像框）、去广告（免广告）。

- 实物奖励：根据积分档次兑换数码周边、充值卡等（需要对接发货系统）。

- 每日限购或总限购。

数据库新增表：

CREATETABLEshop_items(

idINTAUTO_INCREMENTPRIMARYKEY,

nameVARCHAR(100)NOTNULL,--商品名

descriptionTEXT,--描述

typeENUM('virtual','physical')NOTNULL,--虚拟/实物

cost_pointsINTNOTNULL,--所需积分

stockINTNOTNULLDEFAULT-1,--库存，-1无限制

is_activeTINYINT(1)DEFAULT1

);

CREATETABLEpurchase_log(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

user_idINTNOTNULL,

item_idINTNOTNULL,

cost_pointsINTNOTNULL,

statusENUM('pending','completed','refunded')NOTNULLDEFAULT'completed',

purchased_atDATETIMEDEFAULTCURRENT_TIMESTAMP

);

API 接口：

去广告功能：

- 用户购买“去广告”虚拟商品后，生成一个有效期（如30天），在用户JWT中附加ad_free字段。

- 前端据此隐藏广告位。

#### 社区论坛和评论功能

功能描述：

- 为每条哈希数据增加评论功能，用户可发表评论（需登录）。

- 建立独立论坛板块，用户可以发帖讨论密码破解技巧、工具使用等。

- 评论支持点赞、回复。

数据库新增表：

--评论表（关联哈希数据）

CREATETABLEcomments(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

hash_record_idBIGINTNOTNULL,--关联hash_records.id

user_idINTNOTNULL,

contentTEXTNOTNULL,

parent_idBIGINTNULL,--回复的评论ID

likesINTDEFAULT0,

created_atDATETIMEDEFAULTCURRENT_TIMESTAMP

);

--论坛帖子表

CREATETABLEforum_posts(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

user_idINTNOTNULL,

titleVARCHAR(200)NOTNULL,

contentTEXTNOTNULL,

tagsVARCHAR(200),--标签，逗号分隔

viewsINTDEFAULT0,

created_atDATETIMEDEFAULTCURRENT_TIMESTAMP

);

--论坛回复表

CREATETABLEforum_replies(

idBIGINTAUTO_INCREMENTPRIMARYKEY,

post_idBIGINTNOTNULL,

user_idINTNOTNULL,

contentTEXTNOTNULL,

parent_idBIGINTNULL,

created_atDATETIMEDEFAULTCURRENT_TIMESTAMP

);

API 接口：

前端设计：

- 在查询结果详情页下方增加评论区，支持热排序。

- 独立“社区”板块，类似简易论坛。

#### 后台自动爬取与数据入库

#### 功能概述

- 后台定时任务（使用APScheduler或CeleryBeat）定期从公开数据集源爬取哈希-明文对。

- 爬取的数据自动入库，并标记为source_type='public_crawl'，source='crawl'。

- 爬取过程中自动去重（以hash_type+hash_value为唯一键），避免重复数据。

- 爬取日志记录：爬取时间、来源、新增数据量、失败记录等。

#### 公开数据集源

优先级：先接入免费且易获取的数据源（如SecLists、Probable-Wordlists），再考虑付费或复杂的数据源。

#### 爬虫架构

+-------------------++-------------------++-------------------+

|调度器|---->|爬虫Worker|---->|数据清洗模块|

|(APScheduler)||(异步HTTP请求)||(去重+格式校验)|

+-------------------++-------------------++-------------------+

|

v

+-------------------++-------------------++-------------------+

|错误处理模块|<----|日志记录器|<----|入库模块|

|(重试+告警)||(Elasticsearch)||(批量INSERT)|

+-------------------++-------------------++-------------------+

|

v

+-------------------+

|MySQL(hash_records)|

+-------------------+

#### 定时任务配置

#使用APScheduler配置示例

fromapscheduler.schedulers.asyncioimportAsyncIOScheduler

fromapscheduler.triggers.cronimportCronTrigger

scheduler=AsyncIOScheduler()

#每天凌晨2点爬取SecLists

scheduler.add_job(

crawl_seclists,

trigger=CronTrigger(hour=2,minute=0),

id='crawl_seclists',

replace_existing=True

)

#每周一凌晨3点爬取Probable-Wordlists

scheduler.add_job(

crawl_probable_wordlists,

trigger=CronTrigger(day_of_week='mon',hour=3,minute=0),

id='crawl_probable_wordlists',

replace_existing=True

)

#每月1号凌晨4点爬取HIBP（如果付费订阅）

scheduler.add_job(

crawl_hibp,

trigger=CronTrigger(day=1,hour=4,minute=0),

id='crawl_hibp',

replace_existing=True

)

#### 去重策略

- 数据库层面：在hash_records表上建立唯一索引UNIQUEINDEXidx_unique(hash_type,hash_value)，使用INSERTIGNORE或ONDUPLICATEKEYUPDATE进行去重。

- 爬虫层面：在爬取过程中，使用RedisSet暂存已爬取的哈希值（TTL设置为爬取周期），避免重复请求。

- 增量爬取：对于支持增量更新的数据源（如HIBP的API），记录上次爬取的时间戳，只爬取新增数据。

ALTERTABLEhash_recordsADDUNIQUEINDEXidx_unique(hash_type,hash_value);

#### 入库逻辑

asyncdefbatch_insert_crawl_data(data_list:list):

"""

批量插入爬取数据

data_list:[{"hash_type":"MD5","hash_value":"...","plaintext":"..."},...]

"""

insert_data=[]

foritemindata_list:

#格式校验：计算plaintext的哈希值是否匹配

ifnotverify_hash(item["hash_type"],item["hash_value"],item["plaintext"]):

log.warning(f"数据校验失败，跳过:{item}")

continue

insert_data.append({

"hash_type":item["hash_type"],

"hash_value":item["hash_value"],

"plaintext":item["plaintext"],

"submitter_id":0,#系统用户ID

"source":"crawl",

"source_type":"public_crawl",

"status":"verified",#直接标记为已验证

"submit_time":datetime.utcnow(),

"verified_time":datetime.utcnow()

})

ifinsert_data:

#使用批量插入，冲突时忽略（去重）

asyncwithdb_session()assession:

awaitsession.execute(

insert(hash_records).values(insert_data).prefix_with("IGNORE")

)

awaitsession.commit()

log.info(f"成功插入{len(insert_data)}条公开数据")

#### 对用户查询的影响

- 查询优先级：用户提交的已验证数据（source_type='user'）优先返回，公开爬取数据次之。如果用户提交的数据与公开数据冲突（相同的哈希值对应不同明文），以用户提交的为准（因为用户数据经过社区验证，质量更高）。

- 积分规则：公开爬取数据不参与积分计算。用户查询公开数据时，不会增加verify_count（因为不需要验证），也不会触发积分发放。

- 显示标记：在查询结果中，如果是公开爬取数据，显示“来源：公开数据集”标签，并注明数据源名称（如“来自HaveIBeenPwned”）。

#### 错误处理与监控

- 重试机制：爬取失败时，最多重试3次，间隔指数退避（30s,2min,5min）。

- 告警：连续3次爬取失败，通过邮件或企业微信机器人通知管理员。

- 监控指标：

- 每次爬取的新增数据量

- 爬取耗时

- 失败率

- 重复率（去重后实际入库比例）

#### 爬虫模块代码结构

backend/

├──crawler/

│├──__init__.py

│├──scheduler.py#调度器配置

│├──base_crawler.py#爬虫基类

│├──seclists_crawler.py#SecLists爬虫

│├──probable_wordlists_crawler.py#Probable-Wordlists爬虫

│├──hibp_crawler.py#HIBP爬虫（可选）

│├──data_cleaner.py#数据清洗与校验

│├──db_inserter.py#批量入库

│└──utils.py#工具函数（日志、重试等）

#### 总结与后续规划

通过引入后台自动爬取功能，我们解决了初期数据量不足的问题，同时通过source_type字段清晰区分数据来源，保证用户贡献数据的独立性和积分体系的公平性。未来可以进一步：

#### 数据源扩展：接入更多公开数据集，甚至与第三方平台交换数据。

#### 智能去重：对于同一个哈希值对应多个明文的情况，采用投票机制或置信度评分。

#### 数据质量报告：定期统计公开数据与用户数据的冲突率，评估数据质量。

查询功能增强

#### 2. 数据可视化与统计分析

#### 3. API开放平台

#### 4. 安全与隐私增强

#### 5. 移动端与多平台

#### 6. AI与机器学习

#### 7. 商业化与盈利

#### 8. 社区生态深化

#### 9. 技术架构优化

#### 10. 其他创意功能

## 表 1

| 方法 | 接口 | 说明 | 限流 |
| --- | --- | --- | --- |
| GET | /api/search/hash-to-plain | 正向查询（哈希→明文） | 用户限额 |
| GET | /api/search/plain-to-hash | 反向查询（明文→哈希） | 用户限额 |
| GET | /api/leaderboard | 排行榜（按积分/贡献数） | 无限制 |

## 表 2

| 方法 | 接口 | 说明 | 限流 |
| --- | --- | --- | --- |
| POST | /api/auth/register | 注册 | 5次/分钟/IP |
| POST | /api/auth/login | 登录，返回JWT | 10次/分钟/IP |
| GET | /api/user/profile | 获取用户信息 | 无限制 |

## 表 3

| 方法 | 接口 | 说明 | 限流 |
| --- | --- | --- | --- |
| POST | /api/contribute/submit | 提交明文-哈希对 | 20次/天/用户 |
| POST | /api/contribute/confirm | 社区确认（等级≥3用户） | 50次/天/用户 |
| GET | /api/contribute/pending-list | 待验证数据列表（等级≥5可见） | 无限制 |

## 表 4

| 方法 | 接口 | 说明 | 说明 |
| --- | --- | --- | --- |
| POST | /api/tool/submit | 桌面端提交（携带程序标识） | 桌面端提交（携带程序标识） |
| GET | /api/tool/device/register | 设备注册（生成设备ID） | 设备注册（生成设备ID） |
|  |  |  |  |

## 表 5

| 哈希算法 | 积分 |
| --- | --- |
| MD5 | 1 |
| SHA1 | 2 |
| SHA256 | 3 |
| SHA512 | 4 |

## 表 6

| 用途 | 颜色值 |
| --- | --- |
| 主渐变 | #6C63FF → #FF6584 |
| 背景 | #0f0c29 → #302b63 → #24243e |
| 输入框背景 | rgba(0,0,0,0.3) |
| 文字 | 白色 + 半透明灰 |
| 奖牌颜色 | 金 #FFD700，银 #C0C0C0，铜 #CD7F32 |

## 表 7

| 方法 | 接口 | 说明 |
| --- | --- | --- |
| POST | /api/bounty/create | 创建悬赏任务（冻结积分） |
| GET | /api/bounty/list | 获取悬赏列表（支持按状态、算法筛选） |
| POST | /api/bounty/submit-password | 提交密码（solver） |
| POST | /api/bounty/verify | 发布者验证并确认（publisher） |
| POST | /api/bounty/cancel | 发布者取消任务（退回积分） |

## 表 8

| 方法 | 接口 | 说明 |
| --- | --- | --- |
| GET | /api/shop/items | 商品列表 |
| POST | /api/shop/purchase | 购买商品（扣积分） |
| GET | /api/shop/purchase-history | 用户购买记录 |

## 表 9

| 方法 | 接口 | 说明 |
| --- | --- | --- |
| GET/POST | /api/comment | 获取/添加评论 |
| GET/POST | /api/forum/posts | 帖子列表/发帖 |
| GET/POST | /api/forum/reply | 回复帖子 |

## 表 10

| 数据源 | 类型 | 数据量（估算） | 获取方式 | 更新频率 |
| --- | --- | --- | --- | --- |
| Have I Been Pwned (HIBP) | 密码泄露集合 | 8亿+ | 官方API（需付费订阅）或第三方镜像 | 每月 |
| CrackStation 公开字典 | 密码字典+彩虹表 | 15亿+ | 直接下载（torrent） | 不定期 |
| SecLists | 密码字典 | 1000万+ | GitHub仓库 | 不定期 |
| Probable-Wordlists | 密码字典 | 30亿+ | 直接下载 | 不定期 |
| RockYou | 经典密码泄露 | 3200万 | 公开数据集 | 一次性 |
| 其他开源项目 | 各种字典 | 不定 | 爬虫+API | 不定 |

## 表 11

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 批量查询 | 一次提交多个哈希值（用逗号/换行分隔），返回结果列表 | 提升效率，满足渗透测试批量验证需求 | ⭐ |
| 模糊查询 | 支持部分哈希值或明文搜索（如 password*、5d4140*），可基于全文索引（Elasticsearch） | 方便用户快速定位数据 | ⭐⭐ |
| 哈希类型自动识别 | 根据哈希值长度自动判断算法类型（如32位→MD5，40位→SHA1），无需用户手动选择 | 降低使用门槛 | ⭐ |
| 子串查询 | 搜索包含特定子串的明文（如所有包含“admin”的密码） | 安全研究常用，发现规律 | ⭐⭐ |
| 组合查询 | 同时指定多个条件（算法+哈希值+明文长度范围+来源） | 高级用户需求 | ⭐⭐ |

## 表 12

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 热门密码趋势图 | 展示近期查询最多的Top 100密码及变化趋势（按周/月） | 揭示密码使用行为，吸引流量 | ⭐⭐ |
| 算法分布饼图 | 统计库中MD5、SHA1等各算法占比 | 帮助用户了解数据构成 | ⭐ |
| 用户贡献排行榜 | 按积分、贡献条数、验证成功率等维度排名 | 激励竞争，驱动贡献 | ⭐ |
| 数据热度地图 | 展示哈希值查询频次的热点分布（类似GitHub贡献图） | 视觉化呈现热门数据 | ⭐⭐ |
| 密码强度分布 | 分析库中密码的长度、字符类型复杂度分布 | 安全科普，提升用户安全意识 | ⭐⭐ |

## 表 13

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| API密钥管理 | 用户可生成多个API密钥，设置白名单IP、配额限制 | 便于开发者集成 | ⭐⭐ |
| SDK开发 | 提供Python、JavaScript、Java等多个语言的SDK | 降低接入门槛 | ⭐⭐⭐ |
| API市场 | 允许第三方平台购买/调用我们的API（按次/包月） | 商业变现渠道 | ⭐⭐ |
| Webhook通知 | 当用户提交的数据被验证或悬赏完成时，主动推送通知 | 实现自动化工作流 | ⭐⭐ |

## 表 14

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 双因素认证（2FA） | 支持TOTP（Google Authenticator）或短信验证码 | 保护高等级用户账户 | ⭐⭐ |
| 数据脱敏展示 | 默认仅显示明文前2后2字符，鼠标悬浮点击查看完整 | 防止显示敏感信息 | ⭐ |
| 审计日志 | 记录所有API调用、数据修改操作，支持导出 | 合规审计需要（企业客户） | ⭐⭐ |
| 零知识查询 | 采用私有集合相交（PSI）协议，用户查询时服务器不知具体哈希值 | 高级隐私保护 | ⭐⭐⭐ |

## 表 15

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| Flutter/React Native App | 开发iOS/Android原生应用，支持推送通知 | 扩大用户触达 | ⭐⭐⭐ |
| 浏览器扩展 | Chrome/Firefox插件，一键查询选中文本的哈希值 | 便捷查询工具 | ⭐⭐ |
| Telegram/Discord Bot | 在聊天工具内查询哈希值 | 社区互动工具 | ⭐⭐ |

## 表 16

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 密码生成器 | 基于库中常见模式，生成类似真实密码的变体（如加数字、大小写） | 帮助用户创建更安全密码 | ⭐⭐ |
| 自动补全查询 | 用户输入明文时，自动推荐可能的哈希结果 | 提升输入效率 | ⭐⭐ |
| 预测未收录哈希 | 对未在库中的哈希值，基于ML模型猜测其明文（如GAN生成候选密码） | 突破数据量限制 | ⭐⭐⭐ |

## 表 17

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 企业版订阅 | 提供无限查询、批量API、SLA保障、专属技术支持 | B端盈利 | ⭐⭐ |
| 广告系统 | 精确投放安全相关广告（渗透测试工具、培训课程） | 流量变现 | ⭐⭐ |
| 数据导出服务 | 用户可付费下载特定算法子集（如所有MD5映射） | 数据产品 | ⭐⭐ |
| 众包破解任务平台 | 用户发布悬赏破解未收录哈希，平台抽佣 | 交易抽成 | ⭐⭐ |

## 表 18

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 成就徽章系统 | 设置“破冰者”、“哈希猎人”、“积分大亨”等成就徽章 | 增加用户粘性 | ⭐ |
| 好友/关注系统 | 用户可互相关注，查看彼此贡献动态 | 社交化 | ⭐⭐ |
| 组队模式 | 组队参与悬赏任务，按贡献分配积分 | 协作激励 | ⭐⭐ |
| 内容创作 | 允许用户发布文章（密码破解技巧、工具评测），支持点赞/打赏 | 知识分享社区 | ⭐⭐⭐ |

## 表 19

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 冷热数据分离 | 将高频查询数据放在Redis缓存，低频数据存MySQL或对象存储 | 提升查询速度，降低成本 | ⭐⭐⭐ |
| 流式数据处理 | 使用Kafka处理用户提交和爬取数据，实现异步解耦 | 应对高并发写入 | ⭐⭐⭐ |
| 全球CDN加速 | 前端静态资源、API响应通过CDN分发 | 降低全球用户延迟 | ⭐⭐ |

## 表 20

| 功能 | 说明 | 价值 | 难度 |
| --- | --- | --- | --- |
| 弱密码检测服务 | 输入用户名+密码，检查是否出现在泄露库中（类似Have I Been Pwned） | 安全价值高 | ⭐ |
| 哈希计算器 | 在线计算MD5/SHA1/SHA256/SHA512，支持文件上传计算 | 独立工具功能 | ⭐ |
| 字典生成器 | 根据用户指定规则（生日、姓名、数字）生成密码字典 | 渗透测试辅助 | ⭐⭐ |
| 与HashCat集成 | 允许用户下载平台数据作为HashCat字典，或上传HashCat结果 | 打通专业工具链 | ⭐⭐ |
