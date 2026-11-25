# MVP 验证记录

## 2026-11-16 结构化技能自由文本 note 上线

**状态：通过。** `calculate` / `query_earthquakes` 新增可选 `note` 参数：脚本按参数执行不变（`ScriptModel` 以 `script_fields` 白名单剥离 note），note 非空时服务层用共享中转模型（`common.py` 的 `relay_model`，glm-5.3）组织"脚本结果 + 用户补充要求"为最终 answer，LLM 失败回退纯脚本结果。触发场景：用户实测发现输入框提示词只进对话流不参与执行，明确要求参数与提示词共同构成一次技能调用。

- 部署：本地 `runtime/script_agents.py`（SHA-256 `d4b2fa6cf3a0a2697c0e4c00a93c61ae9c594c663a36d66985e8ffacb740f031`）上传至 200 `/root/agent-os-poc/mvp/script_agents.py`，两端哈希一致；原文件备份 `backups/script_agents-before-note-20261116-191134.py`；重启 `agno-mvp-employee` 后 active。
- 验证（服务器本地 JSON-RPC over MCP，令牌仅进程内读取，未落日志）：`tools/list` 的 `calculate` properties 为 `['expression','note']` 且 note 非必填；`tools/call calculate {"expression":"12","note":"告诉我计算的过程和原理"}` 返回完整回答——脚本结果 `12 = 12` + 解析/求值/输出三步过程 + 同一律原理说明，run `99ca7b5f-e56b-4c63-bd41-04ac5ac640d0`，`export_policy=byok_allowed`。本轮真实新增 1 次 Agent 运行（用户在部署选项中明确授权本次验证）。
- 兼容性：旧客户端不带 note 对新服务端无影响；新桌面 bundle（`maipro-company-bundle-1.0.20261116190608.tgz`，84 项测试通过）才发送 note，安装顺序无约束。
- 验证脚本已从服务器 `/tmp` 删除；未改脚本沙箱边界（`env={}`、无网络、无凭据）。

## 2026-11-13 迁移至 192.168.1.200 全新部署

**状态：通过。** 老服务器 166 当日关机不可达，经用户确认在 200 全新部署同架构 AgentOS（root 系统服务），未迁移旧数据，模型改用中转 `glm-5.3`，员工令牌新生成。

- 环境：CentOS Stream 8 x86_64，dnf 安装 python3.12，`.venv-mvp` 安装 `agno[os]==3.1.10` + `fastmcp==4.1.6` + `openai==3.46.0` + `psycopg[binary]` 等对齐 166 版本；pgvector `0.8.7-pg18-trixie` x86_64 镜像经 docker.m.daocloud.io 拉取后 retag（200 无法直连 Docker Hub）。
- 数据库初始化：`setup_postgres.py` 在全新容器内创建受限角色/库/`agentos` schema/vector 扩展并回写 `database_url`；框架 `PostgresDb._create_all_tables()` 一次性建 16 张表，随后 `common.py` 还原 `create_schema=False`。
- 两个插曲已修复：`agno[agentos]` extras 不存在（正确名为 `agno[os]`，fastmcp 需单独安装）；`interview-release.json` 初版误用 20261028.1 旧清单导致 employee 启动校验失败，以 `final-validation-receipt.json` 重建 20261105.1 清单并用 `.context/interview-refresh-20261105/release/` 七文件（哈希逐一比对一致）替换后恢复。本机 `~/.codex/skills` 原件与发布版哈希不一致，不可作为部署源。
- 服务验证：`agno-mvp-admin`/`agno-mvp-employee` 系统服务 active 且开机自启；`/health` 200，`/agents` 列出 calculator-agent 与 http-info-agent；MCP `tools/list` 含 calculate、query_earthquakes、list_company_tasks、get_company_task。
- 业务实测（服务器本机 + Mac 经隧道两种视角）：`(0.1 + 0.2) * 10` 返回 `3`（run `beb8b007-3b9d-48ed-9aac-d0f189f3bcf7`）；`35.68, 139.69` 返回 USGS 真实记录（2026-11-12T13:27:22 UTC，Tako, Japan，4.5 级，run `d40583d8-5b2e-42db-99d9-dbe83984f458`）；`list_company_tasks` 空库返回空列表；无令牌 POST /mcp 返回 401，员工端 `/agents`、`/health` 均 404。
- 模型链路：中转 `43.155.168.149:8080/v1` 的 `/v1/models`、`/v1/chat/completions`、`/v1/responses` 三端点以用户提供的 key 实测可用，`common.py` 无需改动。
- 连接方式：因插件 Host 强制非本机 HTTP 用 HTTPS、且 os.agno.com（HTTPS 页面）对内网 IP HTTP 请求存在 mixed content 拦截，内网直连不可行，改回 SSH 隧道（Mac localhost:7777/7778 → 200）。Mac 凭据 `~/.dsh/.credentials.yaml` 的 `DSH_COMPANY_MCP_TOKEN` 已更新为新令牌；插件 bundle `1.0.20261112203506` 默认 endpoint 即 `127.0.0.1:7778/mcp` 无需改配置；桌面客户端需重启一次以重读令牌。os.agno.com 原有 Local AgentOS 连接（localhost:7777）随隧道自动指向 200。
- 边界：166 历史数据未迁移；200 短时高频 SSH 曾触发一次拒绝，等待自愈（疑似 sshd 并发限制）；隧道未配置断线自动重连与开机自启；桌面端重启后的真实连接表现待用户确认。

## 2026-11-06 计算器与 HTTP 查询

**状态：通过。** 在虚机临时端口及正式端口分别验收，管理端只列出两个新 Agent，员工 MCP 只列出两项执行工具和两项旧历史只读工具。

- 服务端两次调用均实际启动 Python 脚本。计算 `(0.1 + 0.2) * 10` 得到 `3`。查询 `35.68, 139.69` 从 USGS 取回 UTC 2026-11-06 10:39:24.800、地点 156 km SE of Hasaki, Japan、震级 6.1 的目录记录。除零返回中文原因，缺少经度、纬度超界、旧工具调用及未认证请求均被拒绝，员工端管理路由返回 404。
- 正式端口两次成功调用的运行编号为 `98517eb8-be0b-4174-b147-587a6c423e88` 和 `a447e21a-07e8-43d1-97d9-78c0a9fa1c9f`。旧面试历史列表和正文导出通过，数据库只读审计前后均为 38 个会话、44 个运行、16 张表。
- 首次切换遇到 Linux 目录跨父目录移动的权限限制，回退后确认两项旧服务恢复，修正权限设置顺序后重新切换成功。最终备份为 `backups/structured-skills-20261106-111413/`。
- 本地通过两项 Skill 格式校验、计算器 25 项 CLI 用例、HTTP 12 项输入与 6 项 HTTP 分支用例、Python Ruff 和格式检查。客户端通过 82 项测试、类型检查、编译和打包。
- 在正式 Harness 0.2.2-rc.1 的隔离 Web 中安装 Bundle `1.0.20261106191314`，接真实服务。首页计算器输入表达式后得到 `3`。从技能广场打开 HTTP 查询，纬度 91 或缺经度时不可提交，填写有效经纬度后展示 USGS 返回正文。隔离环境的原生开源索引请求返回 404，公司目录及云端任务验证通过。日常桌面安装及 Windows 验收未执行。

证据位于 Agno 与客户端插件仓库各自的 `.context/structured-skills-20261106/`。新员工运行结果未写入 PostgreSQL，当前客户端运行期可查阅。

## 2026-11-05 桌面接通与服务端历史恢复

**状态：PASS。** 用户明确选择“接通桌面并补齐服务端历史”；本轮仅读取已有记录，没有新增测试会话或Agent运行。

- 新增服务端 `mvp/task_history.py`，员工MCP注册 `list_company_tasks`、`get_company_task` 两个只读工具，原两个执行业务工具保留。列表与详情SQL均限定 `user_id=mvp-jax` 和两个业务Agent，连接启用 `postgresql_readonly=True`；不执行DDL、迁移或任何写SQL。只重启员工服务，管理端PID4182未变、`/agents`仍为空。备份 `backups/task-history-20261105-050906/`。
- 只返回输入、时间、状态、运行与会话引用；详情重放既有导出检查，错误/不满足导出条件的运行只给通用提示。没有原始messages、tools、Skill或配置字段。4项离线测试覆盖跨身份拒绝、凭据遮蔽、SQL只读/归属约束、非法游标/编号与分页。
- 真实Host读取当前身份37条业务运行，按2条分页验证前后页不重叠；不存在运行返回null、非法游标拒绝。上次4条运行均可定位，三个成功正文哈希与原交付相同：3905、1820、415字符；首轮错误显示失败提示，不暴露工具原文。
- 公司插件新增history Remote、原生凭据按操作解析、任务列表刷新/分页/加载/错误提示、按run_id去重、同服务端会话轮次回看。48项测试、结构检查、生成、公司包编译、打包和diff检查通过。
- 在用户日常正式macOS Harness **0.2.1-rc.5** 的原生插件页升级并启用 **1.0.20261105131154**。现有测试令牌配置到原生凭据存储（0600），没有进入UI或插件配置；无需给桌面进程手动设置环境变量。界面显示“公司服务已连接”。
- 云端任务页显示 **37条（35完成、2失败）**，最上面4条为12:31、12:36、12:41、12:43的面试验证。打开最新记录后，实际页面展示v1、v1.1、v1.2三轮正文。退出并重新启动客户端，再次恢复公司连接和37条历史，并重新打开相同三轮通过；最终页面停在“云端任务”。未点击提交、未调用个人模型。
- 最终制品SHA-256 `e71c1a5558bd8c7de3878fbf1c50a0d2e4e135c614168436daec508714211614`；四个主要JS在编译、tgz与实际桌面安装中逐字节一致。只读审计仍为 **38会话/44运行/16表**，没有消耗额外运行额度。

证据在 `.context/task-history-20261105/`，其中 `live-history-validation.json`、`installed-artifact.json`、`desktop-result-after-restart.ax.txt`、`final-readonly-audit.json` 保存实际结果。私有凭据不打印或提交。SSH为当前本机回环转发，未配置系统启动自动恢复；本地轮次、草稿与完整混合映射仍不跨重启保存，Windows及新增模型执行未在本轮验收。

## 2026-11-05 面试 Skill 新版部署与真实服务交互

**状态：部署 PASS；两题样卷、同会话续聊与真实公司Host接入 PASS；首轮五题超时 FAIL，长卷与日常桌面未复验。**

用户补充可用SSH认证后连接 `jax@192.168.1.166:22`，恢复本机7777/7778回环转发；凭据未写入仓库或验收材料。测试前获得明确授权：仅独立 `agentos_mvp` 测试库新增最多2个会话、4次Agent运行的虚构资料记录，不改表、迁移、删除或写其他库。该额度本次已全部使用。

### 发布与只读加载

**状态：PASS。** 本机 `java-interview-assessment` 原7文件未改，6文件相较旧20261028.1更新。新版本 **20261105.1**，排序紧凑JSON文件哈希清单SHA-256为 `4dee148a52d056544814a3efdb11b12419a5b26ead668c414c4cb595335bce86`。

服务器实际Agno **3.1.10**，目录 `/home/jax/agent-os-poc/mvp/private-skills/releases/20261105.1/java-interview-assessment/`，逐文件SHA一致、文件0400/目录0500。只绑定该Skill；工具仅说明读取、参考读取与固定模板读取，无脚本、任意文件或Obsidian执行工具。保持原模型 `gpt-6.1-sol`、端点和密钥。清单为 `published` / `jax-mvp-only` / `passed-text-interaction`。

发布基于服务器实时源码与校验保护，未用旧归档覆盖管理端；备份目录 `backups/interview-refresh-20261105-043025/`。员工启动禁用自动建表（`auto_provision_dbs=False`、`create_schema=False`），只重启员工服务。管理服务PID4182未变，`/agents` 仍为空。源码Python语法及本机/服务器最终校验一致。

### 四次真实Agent运行

| 次数 | 入口与内容 | 运行编号 | 结果 |
|---|---|---|---|
| 1 | MCP，虚构简历五题完整样卷 | `e087fe65-730e-4b1d-9906-1ef93bd89602` | ERROR，模型90秒超时 |
| 2 | MCP，12分钟两题完整样卷v1 | `94b55dfd-5dfb-4d7e-aed4-7ee52ac7d162` | COMPLETED，62.7秒 |
| 3 | MCP，同会话修改Q1.3为v1.1 | `6dd35e66-8d80-4c1f-b186-2155a519b32a` | COMPLETED，21.6秒 |
| 4 | 实际公司Host Gateway，带回本地意见修改Q2.2为v1.2 | `1b0dea79-94ab-4e33-975e-9aa29e90f2c1` | COMPLETED，13.6秒 |

首轮会话 `interview-a86fb53875b9429cb2d8cc2cd6b87791`：错误Run的汇总tools为空，但messages确认已读取说明1次、参考2次和模板1次；不能把它判断为Skill未加载。服务日志为模型API超时；随后API超时90→180秒，面试整轮140→270秒，无自动重试。后续缩为两题样卷，未重新验证五题或默认完整长卷性能。

后三次均为会话 `interview-53063227a3da4306bc7c35f46935ff92`，归属固定测试身份 `mvp-jax`、Agent `java-interview-agent`：

- v1包含Spring事务、消息幂等两题，共10个独立评分点，逐点0/1/2锚点、NA和空白得分，按基础60%/项目40%加权；每条口述追问有参考答案，虚构资料明确标识。
- v1.1只澄清Q1.3的异常捕获条件；Q1五行评分点及锚点逐单元格保持一致，Q2不变。
- 当前Codex阅读真实题单后提出“同订单创建/取消是不同合法事件”的本地意见；通过 `packages/company-host/lib/index.js` 的真实Gateway提交同一服务端会话。返回v1.2采用该对照，Q2.2评分行逐单元格保持一致，结果为 `byok_allowed`。
- Host任务 `19e61172-c043-4738-83e5-e531ad1263f7` 完成；415字符正文SHA-256 `0deda38ce161e9c45ba32abd9fc7ef508f59518dafeb26c78f7bc93a19dbe7e0` 与上述第4次持久化Run最后assistant正文一致，不是合成MCP或假模型结果。

### 交付出口与无模型调用检查

**状态：PASS。** 首次成功题单的Agno聚合 `run.content` 夹带158字符工具前过程说明。已修正面试出口为只取最后assistant业务正文；对该已有Run纯函数回放得到3905字符题单，未重新调用模型、未写库，原始响应保留以供核查。后两次真实输出没有过程前缀。

同一出口纯函数检查通过：缺少成功Skill加载、包含凭据、私有路径或超长正文时拒绝导出；保留现有私有原文检测。上述检查不代表完整提示注入防护评估。工具发现仍仅 `ask_private_rules`、`generate_interview_questions`；未发布阶段返回 `not_published`，不存在的续聊会话返回 `session_not_found`，未认证MCP返回401，员工侧 `/agents`、`/sessions`、`/config`、`/registry` 为404。这些探测没有新增Agent运行。

### 持久化范围、回执与限制

只读核对：`agentos_mvp` 会话 **36→38**、运行 **40→44**，仍为原16张表；本次2会话/4运行正好对应1次错误、3次成功。未执行DDL、初始化、迁移、删除或其他库操作。

最终服务器回执 `backups/interview-refresh-20261105-043025/final-validation-receipt.json`；清单 `config/interview-release.json` SHA-256为 `881e1d45c4da49358be3a93d91422f8499e60a2e9c4f71500370df4e04be56a4`。回退业务版本必须保留禁用自动建表设置。

本地证据在 `.context/interview-refresh-20261105/`：`final-validation-receipt.json`、`final-audit.json`、`deliverable-validation.json`、`continuation-validation.json`、`host-continuation-validation.json`、`export-contract-tests.json`、原始三轮业务响应及适配快照。凭据不在证据中。

**范围限制：** 此次为真实服务端与公司Host的文本交互验收，非日常桌面个人模型切换验收。未升级桌面Bundle、注入其环境令牌或改Harness源码；本地意见由当前Codex整理。未测试PDF、真实候选人资料、多员工身份、生产发布或默认长卷；回环SSH转发是当前本机临时连接。后续额外Agent测试须重新核对当前写库授权，不能复用已耗尽额度。

以下保留历史部署与验收证据；最新面试状态以上述2026-11-05记录为准。本地MVP旧实现已归档，归档和恢复说明见仓库根目录 `PROJECT_MEMORY.md`。

日期：2026-10-27。服务器：192.168.1.166。模型：中转 Responses API 的 `gpt-6.1-sol`。

以下保留历次验证记录；当前 PostgreSQL 已迁至宝塔使用的系统 Docker，最新验证见文件末尾。

## 服务与存储

**状态：通过。** 两个 systemd 用户服务均为 active/running，分别只监听虚机回环地址7777和7778。用户 linger 已开启。旧离线服务停止并取消自动启动，保留原文件以便回退。

独立 SQLite 库 `data/mvp.db` 与凭证文件 `config/mvp.json` 权限均为0600。只读查询确认存在 Agent 配置、版本、会话和运行记录。未使用现有 MySQL。

## MCP 功能与出口

**状态：通过。** `check_mvp.py` 使用真实 HTTP MCP 协议执行：

- 未认证调用被拒绝；即使持员工令牌，配置、Registry、Agent、会话、文档及 Server Card 路径仍为404。
- 工具列表只有 `ask_private_rules`；输入仅有 question，没有可伪造的用户或会话 ID。
- 人民币300元工作办公用品返回 `standard_review`，run_id：`c15bf316-934e-41cd-bed9-23e2539aeec7`。
- 人民币800元工作办公用品返回 `manager_review`，run_id：`5fca6d89-04a9-4e43-ab67-09bed800d861`。
- 信息不完整返回 `need_more_info`，run_id：`a828ecce-281a-4512-9cd3-299abdb63e10`。
- 索取 Skill 原文和阈值返回 `refused`，run_id：`22577e8b-a968-486c-96c1-69ce3ddb7805`。
- 输出仅为有限枚举、固定文案、run_id、demo、export_policy；服务端要求成功读取 Skill，才允许导出。

这些是有限场景验证，不代表完整防提示注入或规则推断评估。

## 官方控制台和 Studio

**状态：通过。** 已连接的 Chrome 控制台实际发送了300元办公用品问题，页面显示1次工具调用，并返回 `{"decision":"standard_review"}`。会话 ID：`c85d090b-b1f3-4188-adb5-855cfdef5a98`。

通过与 Studio 相同的 Components API 保存并发布“Studio MVP 验证 Agent”，current version为1；浏览器 Studio 页面已看到该条目。它用于普通 Agent 的配置持久化验证，没有向员工端发布。

## 真实 Codex 客户端

**状态：通过。** Codex CLI 0.154.0 使用本机现有登录和临时独立配置，成功发现并调用 `company_private_rules.ask_private_rules`，返回 `standard_review` 和固定中文结论，run_id：`a4f434fa-66a2-4f28-a65b-76637681d0f3`。

临时测试配置只对已授权的这一个测试工具设置显式批准。日常 Codex 配置仅添加 MCP 连接与员工令牌，保留原有工具审批行为。

## 已处理的验证问题

- 原系统 Python 3.9 不满足新版 MCP 要求；已隔离安装 Python 3.12.16。
- 用户最初指定的 `gpt-5.5` 被中转以404拒绝；用户明确选择后改用 `gpt-6.1-sol`。
- 初次重启后立即请求曾遇到启动未就绪；待两个服务 ready 后重测通过。
- Codex 非交互测试最初停在工具审批；改用单工具显式批准的临时测试配置后，实际调用通过。日常审批配置未改变。

## 最终校验

**状态：通过。** 部署目录的 Ruff 检查、格式检查、Python 编译和差异空白检查均通过。已比对本地与虚机关键源码及 Skill 的 SHA-256，内容一致。最终服务重启后，完整 MCP 集成检查再次通过四类问答和接口隔离验证。

## PostgreSQL 切换验证

**状态：通过。** 用户在本轮明确授权新实例、`agentos_mvp` 数据库、专用账号、pgvector 和 AgentOS 表，切换后保留原 SQLite，不涉及现有 MySQL。

- rootless Podman 的独立容器运行 PostgreSQL 18.6、pgvector 0.8.7，仅发布到 `127.0.0.1:5532`；数据库服务及两个 API 服务均为 active。
- 官方 ARM64 镜像版本 `0.8.7-pg18-trixie`，摘要 `sha256:14d8a514128e8a98150fa391e522e05a8bf70e17bf1a69448fdb7a436c2187c6`，下载与导入均校验内容。
- 应用登录身份和数据库名均为 `agentos_mvp`，超级用户、建库和建角色权限均为 false；表位于 `agentos` schema。
- 已事务性导入11个会话、11条运行记录、1个组件和1个配置版本，并逐字段比对。初次导入发现 PG 独有的可空 `deleted_at` 字段，事务已回滚；适配空字段验证后完整导入通过。
- 原 SQLite SHA-256 保持 `c27beb9051b050d6eea786ae1c787ad74c7a8c185d89a4fef1e3d9870dd648b4`，原文件及额外备份均保留。
- pgvector 实际距离计算返回1.0，证明扩展可正常执行。
- 切换后的完整 MCP 集成检查通过四种问答、鉴权、管理接口隔离及 PG 存储验证；Registry 中未暴露应用数据库密码。
- 已从迁移后的 Studio 配置恢复 Agent，确认实际数据库为 `PostgresDb`；通过 API 执行返回“PG切换验证成功”，原 SQLite 校验值仍未变化。
- 真实 Codex 客户端在切换后再次调用成功，run_id：`afd0a010-61ba-4e14-a348-424fc91ac5a2`，返回 `standard_review`。
- 已生成 PostgreSQL 切换后的一次性备份 `backups/agentos_mvp-after-switch.dump`；此项不代表已配置定时备份。

切换前配置、源码、用户服务和数据库快照保存在虚机 `backups/before-postgres/`。未安装任务沙箱，未启用多员工身份或持久化队列。

## Podman → 宝塔 Docker 迁移验证

**状态：通过。** 用户明确授权将 PG 迁至宝塔 Docker，保留数据并验证 AgentOS 和 Codex 调用。

- 目标引擎为系统 Docker 26.1.4，Compose 2.28.1；迁移前没有其他 Docker 容器或数据卷。
- 将同一 ARM64 镜像导入 Docker，配置 ID 与 Podman 原镜像相同：`sha256:644aabd4345d487db93e9a65f3b0e40af6b7f8b888db8c8d4c827a175902c604`。
- Compose 项目 `agentos-mvp`、容器 `agentos-mvp-postgres`、服务 `postgres`；仅发布 `127.0.0.1:5532`，重启策略 `unless-stopped`，Docker 开机启动已启用，容器状态 healthy。
- 暂停两个 API 后，先记录16张应用表的数据指纹，再导出完整数据库。备份 `backups/before-docker/agentos_mvp.dump` 的 SHA-256 为 `4f303bdd4a08c26009b2a8e44bb51c6ff5fd615c55354389abfd1636696f82ce`；已通过 `pg_restore --list` 验证归档可读取。
- 新 Docker 数据卷为 `/var/lib/docker/volumes/agentos-mvp-pgdata/_data`；创建同名专用角色和空库，以单事务恢复，未复用或改写原 Podman 数据目录。
- 恢复后、API 启动前，对16张表的全部行指纹、行数、表归属、数据库归属、扩展版本和序列状态逐项比对，完全一致。迁移时保留17个会话、17条运行记录、1个组件、1个配置版本及15条 schema 版本记录。
- 原连接配置逐字节保持一致；应用账号的超级用户、建库和建角色权限仍为 false。
- 原 Podman 数据卷保留，Quadlet 移为 `.container.disabled`；两个 API 单元移除旧服务依赖，改为启动前等待数据库就绪。用户默认启动目标不再启动旧 Podman PG。
- AgentOS 健康、配置、Registry、Studio 版本接口通过；pgvector 距离计算通过，原 SQLite 校验值保持不变。
- 完整 MCP 集成验证通过四类问答、鉴权和管理接口隔离。Studio 真实模型调用返回“Docker迁移验证成功”，run_id：`ad222d6e-6039-44a6-86ac-372d40ef0eeb`，新会话确实写入当前 PG。
- 真实 Codex CLI 成功调用 `company_private_rules.ask_private_rules`，返回 `standard_review`，run_id：`abe45428-3d18-4475-9c24-57e799542e84`。
- 已额外生成迁移后的备份 `backups/agentos_mvp-after-docker.dump` 并验证归档可读取；所有备份权限0600。尚未配置定时备份。

本轮部署目录 Ruff、格式、Python 编译和差异空白检查通过。未修改现有 MySQL，未向应用用户授予 Docker socket 权限，也未修改宝塔面板内部数据库。通过系统 Docker 和 Compose 元数据可确认容器已接入宝塔使用的容器引擎；本轮没有登录面板进行界面验证。

## 2026-10-28 最小环境冒烟测试

**状态：基础环境通过，完整市场调研链路未接入。**

- 服务器两个 API 服务 active，管理健康接口正常；Docker PostgreSQL 容器 healthy，实际只读查询确认 `agentos_mvp` 和 pgvector 0.8.7 可访问。
- 发现本机 7777/7778 SSH 转发已断开，恢复后本机健康接口及真实 Codex MCP 调用通过。现有私有规则 Agent 返回 `standard_review`，run_id：`5d009eb5-23da-46d2-a8bf-000c506d9314`。
- 临时 Docker 容器复用本机已有镜像，只读挂载独立 Python 3.12 运行时与 Sorftime 市场 Skill 采集脚本；非 root、只读根文件系统、禁网络、无 Docker socket，限制 1 CPU / 256 MiB / 64 PID，结束后容器自动删除。
- 使用 Skill 文档的示例类目和固定测试输入执行 `--dry-run`，真实 CLI 调用数为0；结果写入独立测试目录，脚本与根目录写入检查均被拒绝。
- 使用简单测试脚本生成 `report-v1.html`、修改文案后生成 `report-v2.html`，用于验证容器文件输出与重生成；这些页面不是真实市场报告，也没有经过市场报告模板渲染或人工确认流程。
- 测试产物位于虚机 `/home/jax/agent-os-poc/smoke-20261028/output/`。市场报告完整渲染依赖 Jinja2 尚未安装，数据源 CLI、采集凭据及市场任务 MCP 工具尚未接入。

本次没有新增数据库表、修改框架或安装常驻任务调度服务。Codex 调用沿用已授权的独立 MVP 测试库保存测试会话。

## 2026-10-28 原生 DockerSandbox 接入 AgentOS

**状态：通过。** 本轮已使用 Agno 原生 provider，替代之前直接 `docker run` 的验证方式。

- 离线构建 `agentos-sandbox-demo:20261028`，镜像 ID `13cbcfcd4f24`。测试执行进程调用原生 `acreate/aexec/aget/adestroy`；AgentOS 的普通模型 Agent 通过受控工具调用执行进程，模型不在容器中运行。
- `check_sandbox_demo.py` 实际验证创建、生成、幂等创建、同容器修改、HTML转义、非法key拒绝、销毁、销毁后旧报告可读，以及新一代容器继续生成和修改。测试容器已清理。
- Chrome 的 os.agno.com 已实际选择“Docker 沙箱演示”，在同一会话 `59dd0530-3913-4356-b197-e281f8b00ddc` 完成两轮交互，每轮均显示2次工具调用。
- 第一轮运行 `e4603ca8-f907-47b0-986f-c713154678d5` 创建并生成 v1；第二轮 `5459f869-1c00-4c6f-be37-b0619d6587fe` 修改并生成 v2；两轮均在 PostgreSQL 中保存为 `COMPLETED`。
- 两轮容器 ID 都为 `3cfe78075ba665b775359e015fa2c2fdcd7350093bc244aa7129fc444f196d15`。实际 Docker inspect 确认 UID1000、ReadonlyRootfs=true、network=none、Memory=268435456、NanoCPUs=1000000000、PidsLimit=64。
- v2 的 SHA256 为 `167be7e15a62ac06e610e4c19c69ebf4babdc57b338210d61210325ee64add31`。Chrome 已实际打开页面，显示“沙箱验证成功”“Agno DockerSandbox 演示 · v2”“第二轮修改完成”，v1仍保留。
- 演示容器闲置15分钟自动销毁，导出的HTML和操作记录保留；当前没有容器工作区检查点或完整coding-harness运行时，没有接入市场数据源与正式报告模板。
- 两个原服务仍 active；管理服务新增演示 Agent，员工 MCP 工具列表未增加。执行进程为独立系统服务，通过本地 Unix socket 调用，仅其服务进程获得 Docker 补充组权限。
- 修改的4个Python文件已通过 Ruff E/F/I、格式检查和服务器Python编译检查。
- 真实 Codex CLI 回归调用现有私有规则 MCP 成功，run_id：`16ded146-c997-4d7c-adff-0fc669e72aca`；员工端的管理、会话和报告路径仍为404，Registry中没有模型密钥。

界面证据保存在本机 `.context/native-sandbox-proof/agentos-chat.jpg` 和 `report-v2.jpg`；部署前管理入口源码备份于虚机 `backups/before-native-sandbox/admin.py`。

## 2026-10-28 公司面试出题 Skill 发布演练

**状态：通过，仅Jax测试范围。** 发布过程由操作者代替尚未开发的发布后台手工完成，没有实现网页上传或通用自动发布。

- 本机Skill为 `java-interview-assessment`，原7个文件未修改，固定版本 `20261028.1`。文件清单总SHA256为 `3d2c94806de9a7a6c2caa1b55e322b437ca6b92246d5b25fd0917d1a819ff8a3`；服务器文件逐一核验并设为只读。
- 纯说明、参考与模板包，不执行脚本，没有构建新镜像、安装依赖、新增凭据或数据库表。新增“Java 面试出题”Agent，只绑定这一个版本；原规则Agent仍只加载演示报销Skill。
- Chrome实际会话 `4cae1c88-b141-424c-b4b3-4ed0cae39190` 使用虚构简历生成5题，基础3题、项目2题，每题5点，共25点评分锚点；记录表为NA、得分空白，没有真实候选人评价。运行 `d49471a6-ac71-4cca-a477-395e65f136a6` 保存为completed。
- 同一会话运行 `68f9ffe8-7b55-45c0-a2ac-487736715b76` 生成题单v1.1，仅澄清Q1。已逐单元格比对五行评分锚点，与v1完全一致，题号及60%/40%权重保留。
- 在发布状态testing时，员工MCP调用返回not_published。验收后将固定Jax测试范围切为published，新增业务工具 `generate_interview_questions`，保留原 `ask_private_rules`。
- 实际MCP检查通过鉴权、工具schema、管理接口404及不存在会话拒绝；不允许caller选择user_id、模型、路径或Skill版本。正向续写也核对了会话及Agent归属。
- 首次Codex调用因可选会话字段传空字符串，被原pattern拒绝，业务未执行。已兼容空字符串作为新任务，使用Pydantic输入适配器验证null、空字符串、合法编号及非法引用。随后真实Codex调用成功，run_id：`40ea515d-e25a-47d5-abc5-6d0bd605677f`，返回Skill版本20261028.1。
- Codex返回会话 `interview-38e1fcb96a1a4f36afb3cd2fda2c5efb` 已经MCP继续修改，运行 `266d40cc-2ac2-4b8a-9b26-46574d408a3c` 成功。原报销工具回归返回standard_review，run_id：`cf3463fb-0329-47a0-94ec-a271c6e80bef`。
- 管理及员工服务均active。相关5个Python文件通过Ruff E/F/I、格式检查，部署文件在虚机通过编译检查。模型密钥与正常Codex工具审批未变更。

题单样本、发布回执、Codex业务结果和控制台截图位于本机 `.context/interview-release/`。服务器样本位于 `data/interview-publish-test/`。当前只验证文本输入和演示发布，不包含PDF解析、网页发布后台、多员工授权或生产化防泄漏评估。

## 2026-10-28 控制台测试条目清理

**状态：通过。** Studio测试组件经API软归档；服务器管理入口移除另外3个演示Agent及报告预览路由，关闭管理端自动建表，仅重启管理服务。原入口备份位于 `/home/jax/agent-os-poc/backups/console-cleanup-20261028-075331/`。

- 健康接口正常，`/agents` 返回空列表；浏览器实际显示“No agents found”。
- 员工服务PID仍为37672，工具发现返回原有两个业务工具，管理接口仍为404；未执行模型调用。只读查询确认29个会话、32条运行、Studio软归档标记及保留的1个配置版本。
- PG应用账号只读登录通过，新增本机5532端口SSH转发并验证可连接；未改变数据库监听范围或凭据。

## 2026-10-28 dbx内网直连PG

**状态：通过。** 按用户要求在服务器Compose中新增 `192.168.1.166:5532:5432`，保留原回环映射；仅重建PG容器，数据卷保持不变且恢复healthy。Mac通过内网IP取得PG协议响应，应用账号经内网地址认证及SELECT查询通过。变更前后29个会话、32条运行、组件及配置版本各1条的行数完全一致；两个API进程未重启，管理健康及员工MCP工具发现检查通过。原Compose及验证基线保存在服务器 `backups/pg-lan-access-20261028-080052/`。
