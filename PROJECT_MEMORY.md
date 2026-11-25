# 公司私有 Skill 平台需求与部署交接

更新日期：2026-11-25，Asia/Shanghai。用于新会话继续当前项目，以本文件记录为交接起点，执行前核查实时服务与代码。当前为 Jax 单人内网测试环境，尚未交付多员工生产平台。

**本地最新状态：** `deploy/agent-os-mvp/` 包含本次 `/v1` 员工产品网关、脚本 Agent、两项 Skill 和部署记录。旧 MVP 演示源码、部署配置和素材的历史归档为 `.context/cleanup-20261028/mvp-deployment-full.zip`，SHA-256 为 `b6697604ef95bb2359b5eef0e0d24b0828dc7938538ad2e1ef3d6719b665e3f5`。逐文件清单见同目录 `mvp-archive-manifest.md`。

## 2026-11-25 架构切换：员工端升级 `/v1/*` 独立云端会话网关（已部署至 192.168.1.200）

配合客户端插件 `1.0.20261125145333`（云端技能改走独立“云端会话”通道，不再注册为原生模型提供方），服务端员工入口 `192.168.1.200:7778` 已从旧版 AgentOS `/agents`+`/sessions` 升级为 `/v1/*` 产品网关：

- **服务端新增与更新（已部署并重启 `agno-mvp-employee.service`，`agno-mvp-admin.service` 未动）**：
  - 新增 `deploy/agent-os-mvp/runtime/v1_gateway.py`（SHA-256 `b7e8e38267fbc8841b19fe11de822af2a3fa2600fdd46403bb9d1a295a28ef73`）与更新 `deploy/agent-os-mvp/runtime/employee.py`（SHA-256 `e07679303a2579bdcf6f020404b1793c4ad49db50213f4c8c68b1d3b5686e318`），离线回归见 `deploy/agent-os-mvp/tests/test_v1_gateway.py`。
  - 员工端口 `0.0.0.0:7778` 仅开放 `/health` 与 Bearer 鉴权的 `/v1/*`（`/v1/me`、`/v1/skills`、`/v1/conversations`、`/v1/conversations/{id}`、`/v1/conversations/{id}/turns`、`/v1/turns/{id}`、`/v1/turns/{id}/events`、`/v1/turns/{id}/cancel`、`/v1/turns/{id}/inputs`、`/v1/uploads`、`/v1/artifacts/{id}/download`）；旧 `/agents`、`/sessions` 返回 404。
  - `/v1` 会话、轮次、幂等键、SSE 事件游标（支持 `Last-Event-ID` 续读）与上传产物元数据持久化在 `/root/agent-os-poc/data/company_v1.db`（SQLite WAL）与 `company_v1_artifacts/`，不改动既有 PostgreSQL `agentos` schema；`script_agents.py`、`common.py`、`admin.py` 均保持未动。
  - 备份与回退：旧版 `employee.py` 备份于 `/root/agent-os-poc/backups/v1-gateway-20261125/employee.py`；回退时还原该文件并 `systemctl restart agno-mvp-employee.service` 即可。
- **本机桌面配置与凭据同步**：
  - `~/.dsh/profiles/desktop/cordis.patch.yml` 的 `company-skills` 配置已改为 `endpoint: http://192.168.1.200:7778`、`tokenRef: DSH_COMPANY_TOKEN`（移除 `/mcp` 路径与 `maxTasks`），并将残留的 `agent-default-model` 从旧 `company-cloud/calculator-agent` 恢复为 `zai/glm-5.3`。
  - `~/.dsh/.credentials.yaml`（0600）已将既有员工令牌同步写入 `DSH_COMPANY_TOKEN`（保留 `DSH_COMPANY_MCP_TOKEN` 便于回退）。
- **实时验证**：直接调用与经 `@maipro/company-host` `CompanySkillsGateway` 实测 `/health`（200）、`/agents`（404）、未鉴权 `/v1/skills`（401）、`/v1/me`（200 `Jax`）、`/v1/skills`（`calculator-agent`、`http-info-agent`）、真实计算器轮次 `(2+3)*4`（SSE `stage`/`delta`/`terminal`，返回 `(2+3)*4 = 20` 并持久化）全部通过。

## 2026-11-23 架构收敛：云端技能 = 原生模型提供方，本地与云端是同一种原生对话

用户反馈旧版两个问题：①对话框里加了“公司技能 / 本地”按钮；②“云端任务”和“工作区”两个历史列表并存。根因是两套并行的界面机制（本地走原生会话；云端走遮蔽原生输入卡的云端输入卡、自绘时间线、独立云端任务页）。已按规划整体收敛，并安装到日常 macOS 桌面。服务端未改动。

- **模型**：本地对话和云端技能对话是**同一种原生对话**，区别只在执行方。Host 经 Harness 官方接口 `ctx.llm.registerAdapter` 把 `/agents` 发现的每个技能注册为提供方 `company-cloud`（界面显示“公司技能”，带“云端”徽标）下的一个模型。侧栏技能入口或技能广场“开始对话”即云端对话；原生模型选择器里选回个人模型即本地对话；同一条对话内可切换。云端回答由 Harness 模型循环记成助手消息，原生消息流、流式输出、停止、历史持久化、会话列表全部复用。
- **已拆除**：全局 execution 开关、云端输入卡（遮蔽 `conversation.composer.bar`）、自绘时间线工作台（HybridWorkbench / HybridController / NativeSessions）、`company-tasks` / `company-history` 面板、侧栏“云端任务”分组、“交给本地模型继续 / 交回公司云端”按钮、自绘模型选择器。
- **公司差异仅三处官方槽位注入**：`conversation.input.dock` 参数条、`conversation.session.header.actions` 的“云端 · 技能名”、`sidebar.session.row.trailing` 的云图标。参数条：必填未填齐时经官方 `conversation.blocks` 让原生输入卡不可发送；参数暂存到 Host；“执行”在输入框为空时把参数行填入输入框再提交；发出后收起为一行摘要，值保留。
- **Host 要点**：`static inject = ['llm']` 必须保留，缺它则注册在模型服务就绪前被静默跳过；只发送用户最后一条消息，参数行拼在前面；服务端会话标识随结束分片的 replayState 写入会话日志、下次从历史助手消息读回（重启后续接同一服务端会话）；带 purpose 的辅助调用（标题生成、上下文压缩）一律拒绝；该提供方不自动重试；失败不把服务端文案当回答流出；`selectSkillModel` / `selectPersonalModel` 只改目标会话、不动全局默认，原生选择器把默认改成技能时在新 Agent 创建时恢复为个人模型。
- **UI 入口必须导出 `inject`**：重写入口时漏掉这一行，导致公司界面不激活且没有任何报错（隔离环境与桌面均复现）；已加回并有回归用例。
- **验证**：12 个测试文件 54 项通过，`pnpm pack:bundle` 完整流程通过；隔离 Web 与日常 macOS 桌面（均 0.2.2-rc.3）实测通过——参数条阻塞 / 执行 / 摘要、云端回答在原生消息流流式显示、新建对话回到个人模型、技能广场与侧栏技能入口、官方界面与公司界面往返。Windows 未验证，未 commit / push。
- **制品**：`artifacts/maipro-company-bundle-1.0.20261123185810.tgz`（79 文件），SHA-256 `ad76b5f32eb1…657897d7`；日常 macOS 桌面已安装。更早的 bundle 与本轮中间包（已移入 `artifacts/archive/`）不得使用。
- **已知边界**：技能对话中原生的本地工具与权限开关仍可见，但不会被触发；云端“调用工具中”的阶段反馈未映射到界面；跨设备的云端历史没有界面入口（Host 的 `history` Remote 保留）；服务端结果当前全部按可进入个人模型处理；固定技能与参数草稿仅保留在当前窗口。
- **排查方法可复用**：插件显示“运行中”但界面不出现且没有报错时，先查入口是否导出 `inject`。仓库自带的 `loader.client.spec.ts` 能在本地加载构建产物并复现激活问题，比在隔离环境里抓控制台更快。桌面“添加插件 → 安装第三方插件”填 tgz 本地路径即升级，完成后自动切回公司界面。验证期间在服务端产生 5 次计算器运行记录，其中 3 次因模型中转临时不可用失败（约 18:30 恢复）。

## 2026-11-17 架构切换：MCP 废弃，全链路走 AgentOS 原生 Agent 运行 API

用户定调（"执行逻辑完全不对"）：公司技能 = 云端 AgentOS 上的真 Agent Runtime，客户端是瘦终端（表单+输入框+流式渲染），不造任何自研协议，一切用 agno 现成能力。已全链路上线：

- **服务端（200 已部署验证）**：`script_agents.py` 删掉自创 ScriptModel，换 agno 标准 `Agent(model=relay_model, tools=[沙箱脚本函数], db=db)`；`employee.py` 白名单 `/agents`+`/sessions`+`/health`（MCP 已 404 下线），`AgentOS(db=db)` 接会话落库。备份 `backups/*-before-agents-20261117-114523.py`。实测：GET /agents 返回技能+工具参数 schema；POST runs（**multipart form**：message/stream/session_id/user_id）stream=true 走 SSE（RunStarted/RunContent 增量/RunCompleted，含 run_id+session_id）；GET /sessions?component_id=&user_id=（分页 page/limit）；GET /agents/{id}/runs?session_id= 返回 run_input/content；POST /runs/{id}/cancel 真取消。
- **Host（company-host 重写）**：Gateway 直连原生 API。catalog=GET /agents（动态技能+inputFields 从主工具 schema 投影，**删了硬编码 CATALOG**）；submit=POST runs SSE 流式读取（RunContent 渐进写 task.result，轮询 getTask 即准流式）；history=逐技能 sessions→runs 合并（RecordedTask：id=`server:{run_id}`、input=run_input）；cancel=真服务端取消；endpoint 自动剥 `/mcp` 尾巴兼容旧 profile；Config 新增可选 userId（默认 mvp-jax）。
- **contracts**：`SkillId=string`（动态 agent id）；`SubmitRequest={skillId, message, sessionId?}`（参数拼进 message："label：value" 行+空行+自由文本）。
- **UI（company-ui）**：技能动态发现（新技能零客户端改动）；**删除客户端拼上下文**（云端 message 原文+服务端 session 多轮，本地轮保留背景+引用拼装）；轮次流式渲染（running 且 result 非空即渐进渲染 markdown，操作按钮完成后出现）；参数表单按动态 inputFields 渲染。
- 测试全量改写：gateway.spec 用 HTTP/SSE fixture；85/85 通过。bundle `maipro-company-bundle-1.0.20261117120531.tgz`（SHA-256 `5b055341…`）。**旧 bundle 与新服务端不兼容（MCP 已下线），必须同装此版**。
- 旧 MCP 时代历史（task_history 37 条）不再可读；新历史走 AgentOS sessions/runs。generate_interview_questions/ask_private_rules 两个旧技能不再存在（未注册为 Agent），如需恢复按新形态发布。

## 2026-11-16 结构化技能自由文本 note 上线

用户实测反馈"输入框提示词只进对话流不参与执行"，确定交互铁律：**必填参数在输入框外部联动参数条，输入框永远写自然语言，两者共同构成一次技能调用**。已全链路上线：

- 客户端（插件仓库）：SubmitRequest 结构化分支加 `note?`（≤2000 字符）；提交后参数条收起为一行摘要（值保留、点"修改参数"回填展开）；bundle `maipro-company-bundle-1.0.20261116190608.tgz`。
- 服务端（200 `/root/agent-os-poc/mvp/script_agents.py`，已部署并重启验证）：`calculate`/`query_earthquakes` 加可选 `note`；`ScriptModel` 以 `script_fields` 白名单剥离 note 后喂脚本（沙箱边界不变）；note 非空用 `common.py` 的 `relay_model`（glm-5.3 中转）组织"脚本结果+用户要求"，LLM 失败回退纯脚本结果。真实调用验证通过（TEST_LOG 2026-11-16 节）。
- **200 的 SSH 密码与全局配置里的不同**（全局密码验证失败），用户当日提供新密码；服务器侧实际文件布局为 `mvp/*.py`（本地 `runtime/` 目录对应虚机 `mvp/` 根，无 runtime 子目录），backups 目录为本次新建 `/root/agent-os-poc/backups/`。
- 回退：恢复 `backups/script_agents-before-note-20261116-191134.py` 并重启员工服务即可。
- **已知坑（2026-11-16 当晚回归）**：pydantic Optional 生成的 tool schema 中 note 为 `anyOf:[{string},{null}]+default:null` 形态；Host 的 `inputFields` 若在剥离 note **之前**用严格 fieldSchema 解析 properties，会解析失败并导致**整个能力目录加载失败**（客户端表现为"能力目录加载失败"、技能 0）。修复版 Host 先用 `wire.unknown()` 宽松接收 envelope、剥离 note 后再逐字段严格校验；gateway.spec 的 fixture 已 1:1 复刻该 anyOf 形态防回归。修复 bundle：`maipro-company-bundle-1.0.20261116192050.tgz`。

## 192.168.1.200 全新部署（2026-11-13，当前生产测试环境）

老服务器 166 当日已关机不可达（ping 与 22 端口均不通），其 38 会话/44 运行旧数据与原 `config/mvp.json` 均无法取出，200 为**全新空库部署**，未迁移历史数据。部署经用户确认三项决策：模型改用中转 `43.155.168.149:8080/v1` 的 `glm-5.3`（key 由用户当日提供，已实测 chat 与 responses 端点均可用）、服务绑定方式、员工令牌新生成。

| 项目 | 当前值 |
|---|---|
| 服务器 | `192.168.1.200`，SSH 用户 `root`，端口 22，CentOS Stream 8 x86_64，内存 7.4G |
| 服务根目录 | `/root/agent-os-poc`（root 系统服务，非 166 的用户服务+linger 模式） |
| Python | dnf 安装 `python3.12`（3.12.1），虚拟环境 `.venv-mvp`；依赖 `agno[os]==3.1.10`、`fastmcp==4.1.6`、`openai==3.46.0`、`psycopg[binary]` 等对齐 166 版本 |
| 数据库 | Docker `agentos-mvp-postgres`（pgvector 0.8.7-pg18，经 daocloud 加速器拉取 x86_64 镜像后 retag），Compose 文件同 166 结构，绑 `127.0.0.1:5532`，卷 `agentos-mvp-pgdata`；16 张 agentos 表已建（与 166 基线一致，含 eval_runs/schema_versions 演进表名） |
| 服务 | `agno-mvp-admin.service`（127.0.0.1:7777）、`agno-mvp-employee.service`（127.0.0.1:7778），均 enable 开机自启 |
| 模型 | 中转 `http://43.155.168.149:8080/v1` + `glm-5.3`，Responses API 可用，`common.py` 的 `OpenAIResponses` 未改动 |
| 员工令牌 | **新生成**（`dsh-` 前缀 47 字符），服务器存 `/root/.employee-token-200`（0600）；Mac `~/.dsh/.credentials.yaml` 的 `DSH_COMPANY_MCP_TOKEN` 已同步更新 |
| 部署源码 | 本地 `deploy/agent-os-mvp/runtime/`（admin/employee/script_agents）+ `.context/structured-skills-20261106/stage/mvp/` 的 common/interview_agent/task_history + 归档 wait_database/setup_postgres/compose + `.context/interview-refresh-20261105/release/` 的 20261105.1 Skill 七文件（本机 `~/.codex/skills` 原件与发布版哈希不一致，不可用于部署） |
| 发布清单 | `config/interview-release.json` 由 `final-validation-receipt.json` 的 release 字段重建（stage=published）；**不能用 `.context/interview-release/interview-release.json`**（20261028.1 旧版指向错误路径） |

**连接方式：员工插件内网直连（2026-11-16 定稿），管理员继续 SSH 隧道。** 用户明确否决公网域名方案（"我就内网用用"），要求像前端 local/prod 配置一样切换环境。落地分三层：

1. 插件侧（`ai-workspace-client-plugins`，commit 待提交）：`company-host/src/index.ts` 的 endpoint 校验放宽——HTTP 除本机外同时放行 RFC 1918 私网 IP（`10/8`、`172.16/12`、`192.168/16`），公网 IP 仍强制 HTTPS；新增网关测试覆盖私网放行与公网拒绝（83 项全过）。新制品 `artifacts/maipro-company-bundle-1.0.20261116162906.tgz`（89 文件）。**桌面 bundle 更新到该版本后才能连内网地址**。
2. 服务器侧：`agno-mvp-employee.service` 改绑 `0.0.0.0:7778`；`employee.py` 的 `allowed_hosts=[]` 改为 `["192.168.1.200"]`（框架 DNS 防回环校验只默认放行 localhost，内网 Host 头不加白会 400 `invalid_host`——这是内网直连首次失败的根因）。管理端 7777 保持 127.0.0.1 仅隧道可达。本地 `deploy/agent-os-mvp/runtime/employee.py` 已同步。
3. 配置切换：桌面/员工 profile 的 `cordis.patch.yml` 对 `id: company-skills` 做 config 整体覆盖（**注意 profile 层是整体替换不是合并，必须写全 endpoint/tokenEnv/timeoutMs/maxTasks/maxConcurrent 五个字段**），endpoint 填 `http://192.168.1.200:7778/mcp`；员工分发形态即"装 bundle + 配内网地址 + 发令牌"。本地开发仍用默认 `http://127.0.0.1:7778/mcp`。

2026-11-16 隔离 Web 端到端验证：新 bundle + 内网 endpoint 直连，技能广场加载 2 个公司技能，工作台执行 `(0.1+0.2)*10` 返回 `3`，全程无 SSH 隧道；截图 `output/playwright/intranet-direct-calculate.png`。隔离环境注意：`.credentials.yaml` 的 browser-session secret 需 43 位随机串（43 字符 base62 形状），短串会被拒。os.agno.com 管理页（HTTPS 页面）对内网 IP HTTP 存在 mixed content 拦截，仅 localhost 豁免，故管理员仍走隧道：

```bash
sshpass -p '<密码>' ssh -nN -f -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:7777:127.0.0.1:7777 -L 127.0.0.1:7778:127.0.0.1:7778 root@192.168.1.200
```

隧道为易失进程（Mac 休眠/重启即断，11-16 已发生一次），未配自动重连；员工插件内网直连不依赖隧道。

166 的全部历史章节继续保留在本文档下方作为交接记录；其服务、数据、隧道配置均已随关机失效，恢复 166 前不要按旧地址操作。

**控制台最新状态（2026-11-06）：** 管理端仅列出 `calculator-agent` 和 `http-info-agent`。员工 MCP 发布 `calculate`、`query_earthquakes` 及两项旧历史只读工具。旧能力已退役，历次旧 Agent 和运行编号是历史记录。

恢复时先核对归档校验值，解压到独立临时目录，按需恢复代码并比对服务器版本；保留当前记忆，不用旧文档快照覆盖。不要用带删除选项的同步命令将本地文档目录覆盖服务器部署目录。

## 执行位置入口即位置 + DSH 兼容下限 + rc.2 工作区修复（2026-11-12，最新客户端状态）

用户当日反馈三个问题并全部解决（插件仓库 `docs/verification.md` 顶部三节有完整验证记录）。

其一：云端/本地执行位置难选。根因：所有公司能力本就只能云端执行（结构化技能静默拒绝本地、本地轮无 skillId），“本地”实为员工自选模型的原生会话，位置由“选没选技能”唯一决定。最终产品语义经用户确认：**选公司技能即云端对话，新建对话即本地，完全移除执行位置切换器**（置灰降级中间版被否决后彻底移除）。跨端接续改为显式按钮：云端结果“交给本地模型继续”不变，最新完成本地结果卡新增“交回公司云端继续”。`executionAffinity: 'cloud-only' | 'any'` 与 `executionNote` 发布期声明、云端卡选择器“云端执行”标注保留（未来发布后台“选择运行环境”落此字段）。

其二：客户端每次升级插件即失效。根因：`engines.dsh` 为精确版本 OR 列表；Harness 官方校验为 `semver.satisfies(runtime, range, { includePrerelease: true })`，本就支持范围。按用户确认语义**只限历史、不限未来**：统一声明 `">=0.2.1-rc.2"`，`supportedDshVersions` 改 `supportedDshRange`，verify-structure 用 semver 校验（禁止上限），根 package.json 新增 semver@7.8.5。官方另有逐版本豁免 `dsh plugin allow-version`，不作常规手段。

其三：0.2.2-rc.2 公司界面左侧工作区整个消失（官方界面正常）。隔离 Web（桌面随附 rc.2 CLI + 隔离 DSH_HOME）复现并捕获真实错误：`TypeError: useSectionScroller is not a function at WorkspaceBrowser`。根因：rc.2 为 `sidebar.workspaces` 槽位新增宿主 hook 供给，要求声明方在 children 提供 `inject: { hooks: { sectionScroller: (standard, hookContext) => hookContext.useSectionScroller } }` 且宿主 `renderSlot` 第三参传 `{ hookContext: { useSectionScroller } }`；公司侧栏两者皆缺，WorkspaceBrowser 崩溃落 `data-slot-error` 占位。修复在 `layout.tsx` 两处（声明侧工厂转发 + 渲染侧稳定 hookContext，公司布局各区独立滚动无需手势交接）。**注意：仅传 renderSlot 第三参（中间版 1.0.20261112202832）无效，声明侧工厂是必要的一半**。排查方法可复用：隔离 Web + 页面注入 console.error 捕获器 + 官方↔公司切换触发重渲染拿真实错误。

**当前最终制品 `artifacts/maipro-company-bundle-1.0.20261112203506.tgz`（89 文件），SHA-256 `fa82144c14f754c98d829b21b5d022c3fa6286d10e5b64601e7b0629ca5a3f41`**（含当日全部三组改动）。82 项测试、rc.2 隔离 Web 回归（工作区树恢复、双向切换、console 零错误）通过。打包用系统 Node 22.21.0（桌面内置 Node 24 因 macOS 库验证拒绝加载 rolldown 原生绑定）。**员工桌面旧安装须更新到 `1.0.20261112203506`**；未连接真实公司服务或模型，未 commit/push。

## 计算器与 HTTP 查询（2026-11-06）

内网测试机 Agno 3.1.10 已发布两个脚本 Agent。员工 MCP 的 `tools/list` 提供必填字段与校验范围，Host 投影到客户端首页及对话页。计算器接收 `expression` 字符串，HTTP 查询接收 `latitude` 与 `longitude` 数值，固定查询 USGS 地震目录。两个 Agent 执行确定性 Python 脚本，无模型调用，员工任务结果留在当前客户端运行期。

原制度问答和面试出题已下架，旧 Skill 目录归档到服务器 `backups/structured-skills-20261106-111413/private-skills`。旧历史继续通过只读 MCP 查阅，切换前后 PostgreSQL 都是 38 个会话、44 个运行、16 张表。部署及验收见 `deploy/agent-os-mvp/README.md` 和 `TEST_LOG.md`。

客户端 Bundle `1.0.20261106191314` 通过 82 项测试，在正式 Harness 0.2.2-rc.1 的隔离 Web 验证真实表单与两项服务端执行。制品 SHA-256 为 `549fff453c33c4f93e2b33d2ac8458a7478871706230396af9f48edfdfa5fd7e`。日常桌面与 Windows 未执行安装验收。

## 技能广场与 Company MCP 对齐（2026-11-06）

按 AmazonAIWorkspaceUI 远端 `1d42993` 对齐技能广场、Company MCP 菜单与页面，实现在独立插件仓库。技能广场支持来源／分类／搜索／详情、固定或移除左栏、使用时创建云端会话、原生插件及内置状态。Company MCP 支持批量固定、刷新实际网关状态、管理本机可写 MCP 连接器；公司网关未提供集群、工具数或桥接子服务明细，不采用原型数据。第三方安装继续由 Harness 原生安装界面处理。

候选 `1.0.20261106173319`，SHA-256 `fb7577378660b0b6d700525f651f7f1fb8b5b659bfa644883d07cbbc48aea070`。81 项测试通过；正式 Harness 0.2.2-rc.1 的隔离 Web 使用 26 条合成索引和本机合成 MCP，验证搜索与分页、固定和移除、批量同步、可写连接器启用与恢复、原生安装入口、亮暗及 520px 无横向溢出。无真实模型、公司任务或数据库操作。日常桌面未更新，Windows 未验收。制品、截图与断言见插件仓库 `docs/verification.md`。

## 首页对话框复用原生界面（2026-11-06，最新客户端状态）

用户要求对话区复用官方原生界面，公司差异仅保留一个“公司云端/本地”切换和云端输入卡。最终候选版为 `1.0.20261106150852`：hero 行存在时只显示 hero 切换，dock 仅作为无 hero 的对话态兜底；云端模式显示公司输入卡和“云端执行”，不显示模型；本地模式创建/打开原生 Harness 会话并恢复官方模型选择。通用“新建对话”默认本地，公司技能入口仍默认云端。

本轮根据正式桌面问题纠正两处实现：空白 Session 同时挂载 hero 与 dock 导致重复入口；工作区 observable 的 `subscribe` 实例方法被裸传给 React 后丢失 `this`，云端卡崩溃并回退成本地原生输入栏。现已显式绑定订阅对象，并将动态 bar 注册保留在声明期 slot effect 内，状态变化只注册/释放 entry。`conversation-seats` 回归使用依赖实例上下文的 observable，可直接捕获旧崩溃。

云端结果的本地接续已变成显式主流程：`export_policy=byok_allowed` 的最新云端结果提供“交给本地模型继续”，点击后留在同一混合时间线，切本地、创建/复用映射 Session、显示模型选择并聚焦输入框；本地 prompt 会携带已完成云端交付正文。本地完成后可再切回云端，携带本地结论并复用原服务端面试 `session_id`。`display_only`、未知或缺失导出策略的结果不提供按钮，控制器仍拒绝外发。

12个测试文件71项、桌面内置 Node 24.21.0 下 `pnpm check`、完整 verify、pack:bundle 和 diff 检查通过。使用正式桌面随附 DSH `0.2.2-rc.1`、隔离 `DSH_HOME`、合成公司 MCP 与合成本地模型实测三轮：云端题目→一键本地分析→本地建议回传原云端会话；请求核对确认双向正文及 `session_id`，控制台0错误0警告。制品 `artifacts/maipro-company-bundle-1.0.20261106150852.tgz`，SHA-256 `d4f4f2c906b38994600db3dad9dadb406c16c457331374d4810bd8db11cd5837`。证据见插件仓库 `docs/verification.md`、`output/playwright/cloud-local-cloud-handoff-fixed.png`、`.context/handoff-fix-20261106/`、`.context/hybrid-20261102/requests.jsonl`。

此前 `1.0.20261106133721` 的验收漏掉正式桌面保留空白 Session 的双槽并存与实例绑定；`1.0.20261106142106` 也存在上述缺陷；`1.0.20261106142924` 虽修复入口和云端卡，但没有把云端结果的一键本地接续显式呈现，三版均不得作为最终可用版。当前员工桌面实时安装仍为 `1.0.20261106142106`，必须通过桌面插件管理页更新最终候选后才能宣称桌面修复完成。无真实模型/公司任务/数据库操作；亮色与 Windows 未在本轮单独复验。

## 本轮尝试已撤回（2026-11-05）

用户明确要求撤回“只保留官方页面”的误解方案。源码和桌面插件均已恢复到 `1.0.20261105160055`，四个编译 JS 与该原包及实际安装逐字节一致。此前已有未提交改动保留。本轮新增源码及候选包移入插件仓库 `.context/withdrawn-native-extension-20261105/`，不应再次安装。

用户真正要求：仔细对照最新 AmazonAIWorkspaceUI Figma 源码，保留自己的公司 UI 布局，官方已有会话/工作区能力应复用，避免过度改造；不是撤掉公司 UI。本轮已停止设计开发。候选版曾执行只读服务端历史恢复，在本地原生会话中产生历史副本和一个验收草稿；未删除这些本地记录，未执行新模型运行、SQL或服务端部署。原服务端记录未改动。该候选版导入存在官方 blank 会话投影不兼容，未通过实际历史显示验收，不可宣称可用。

## 统一会话历史（2026-11-05，最新客户端状态）

用户明确要求任务按会话维度展示。独立插件已在日常macOS rc.5更新为 `1.0.20261105160055`：“云端任务”改为“对话历史”，左侧与历史页共用会话投影和打开逻辑。按已确认task/session/skill关联聚合云端多轮与已映射本地轮次，合并原生会话和草稿，原生localSessionId去重，不按文本猜测旧记录关联。按最后活动排序，摘要区优先已读取最新回复，否则标最近需求；会话统计、内容搜索和需要关注筛选。打开完整已加载时间线并停最新结果；单轮执行信息留在详情。此设计替代上一轮以单次执行为列表单位的方案。

60项测试、公司包生成/编译/打包及四JS安装一致性通过。桌面37次云端执行聚合33条云端会话，加1条原生本地会话，共34；面试三轮一个入口且完整保留，旧轮次搜索、侧栏首次恢复、原生本地打开、关注筛选、亮暗、751px/520px宽通过。恢复两个固定技能和亮色，停对话历史。制品SHA-256 `c63be09c51f32ccc6f757426cfbf9b7378d33b3553318985cceb325fe9210928`，证据插件仓库`.context/conversation-history-20261105/`。无模型执行、SQL或服务器部署，未提交推送。

展示统一不代表完整混合映射/草稿已跨重启持久化；原生历史仍由Harness保存、云端历史从服务器读取。分页提示当前已加载范围，正文按需读取。Windows、重启及新增执行未在本轮复验。

## 云端任务精确定位（2026-11-05，最新客户端状态）

用户反馈点击不同任务均看到相同内容。原列表每行是单次执行，但同session聚合后统一滚到最后一轮。已在独立插件修复：保留所选task ID，打开完整对话并滚动/聚焦该轮结果，显示“当前查看的执行”、轮次、时间；增加返回云端记录，说明每行执行含义。普通侧栏切换/新轮次清除定位，不改变上下文和续聊语义。

日常macOS rc.5已原生更新至 `1.0.20261105150725`，56项测试及公司包生成/编译/打包通过，四JS与安装一致。桌面逐条实测12:36/12:41/12:43分别停在v1/v1.1/v1.2，制度记录打开另一对话；37条历史只读，无新模型运行、服务器部署或SQL。恢复两个固定技能，停首轮面试结果。制品SHA-256 `11572f7f4f5a1fba4fe89c481671441bde14f19ed03586f848a407e7b2a18d77`。证据在插件仓库`.context/run-focus-20261105/`与`docs/verification.md`。本轮不改变持久化范围，未复验Windows/窄窗口，未提交推送。

## UI/UX 审查修复（2026-11-05，最新客户端状态）

用户要求修复整体审查发现的全部问题。独立插件最终版 `1.0.20261105144826` 已在日常macOS Harness rc.5原生更新启用。技能快捷入口新建独立云端对话；草稿可从统一对话列表找回；合并原生/混合/草稿搜索及工作区分组，以localSessionId去重；超时增加精确任务/运行的只读核查、历史和新建入口，不自动重发。交接预览显示完整实际请求与结果；结果可展开阅读、复制全文，长表换行且阅读历史时不强制跳底；修复插件页面包屑、无效技能筛选，精简统计/说明/一级导航。

55项测试、公司包生成/编译/打包和四JS安装一致性通过。桌面实测37条历史和面试三轮、草稿恢复、入口隔离、统一搜索、原生历史/工作区管理及切回、复制/弹窗、亮暗、751px及客户端最小520×600窗口；抽屉切页自动收起。最终恢复两个固定技能和亮色，停在三轮面试对话。制品SHA-256 `562990d6cb54d161ff9260456966a390793518ad8a5b853a039a8319bf4d82e3`。证据在插件仓库`.context/ux-fixes-20261105/`与`docs/verification.md`。

本轮无新模型运行、无服务端部署、无SQL；原2会话/4运行授权仍已耗尽。回执全丢且无runId时无法自动确定服务端记录，仍需人工核对，不猜测关联。完整混合映射/草稿/固定技能仍为窗口内存，不宣称跨重启持久化。Windows、375px手机及系统最大字号未在本轮实测。Harness源码干净，未提交推送。

## 桌面对话导航优化（2026-11-05，最新客户端状态）

用户确认将工作台右上角协作对话切换器移至左侧。独立插件已打包并在日常macOS rc.5原生更新为 `1.0.20261105135849`。左侧“最近对话”切换已打开的混合对话，顶部仅显示同一标题；服务端面试历史显示“面试题生成 · 11/05 12:36”，三个云端轮次共用一个入口。原生本地会话仍保留在工作区。48项测试、编译打包与实际历史打开/左侧切回/亮暗及折叠检查通过；本轮仅界面和已有历史读取，无新模型运行、无服务端部署或数据库写入。最近对话仍为窗口内存，重启后从云端历史重新打开。证据在插件仓库 `.context/conversation-nav-20261105/` 和 `docs/verification.md`；制品SHA-256 `73fdf81ed13aec47476478a0ef92ce4be01479d90aacfe4c0c09be630c776b1c`。

## 桌面连接与服务端历史（2026-11-05，最新状态）

用户指出桌面“云端任务”没有上轮执行记录，并明确要求“接通桌面并补齐服务端历史”。已在服务器新增只读 `list_company_tasks` / `get_company_task` MCP工具，保留原两个执行业务工具。查询同时限定固定测试身份 `mvp-jax` 和两个业务Agent；按游标分页，只返回任务输入、时间、状态、会话/运行引用和经现有导出检查的业务结果，不返回内部messages/tools/Skill原文。未新增数据库表或写入业务记录，仍38会话/44运行/16表。

当前日常macOS桌面为Harness **0.2.1-rc.5**，原生插件管理页已安装并启用Bundle **1.0.20261105131154**。制品 `/Users/zhulinfeng/Documents/GitSpace/ai-workspace-client-plugins/artifacts/maipro-company-bundle-1.0.20261105131154.tgz`，SHA-256 `e71c1a5558bd8c7de3878fbf1c50a0d2e4e135c614168436daec508714211614`。四个主要编译JS在编译、tgz与实际安装中一致。

Host已从固定启动环境读取改为按操作解析Harness原生credentials引用；现有公司测试访问令牌已存入本机原生凭据提供方，文件0600，值不进入UI、插件配置或日志。客户端显示“公司服务已连接”，历史37条（35成功、2失败），最新四条为本次面试验证。已从桌面打开最新记录，恢复同一云端会话的v1/v1.1/v1.2三轮；退出并重新启动正式客户端后再次恢复连接、37条记录及三轮正文通过，最终页面停在“云端任务”。没有点击提交、调用个人模型或新增Agent运行；上一任务2会话/4运行额度仍已耗尽。

UI新增历史刷新、分页、加载/失败提示、run_id去重和同会话云端轮次聚合；可沿用原session_id继续。**仅云端记录可重新读取；本地轮次、草稿、尚未落库的窗口任务及完整混合映射仍在内存。** 不能把这次桌面真实历史回看称为个人模型交接或完整混合时间线持久化验收。SSH仍为本机当前回环转发，客户端重启不影响；未配置机器重启后的隧道自启动。

服务端新模块为 `mvp/task_history.py`，员工入口同步更新，只重启员工服务；备份 `/home/jax/agent-os-poc/backups/task-history-20261105-050906/`，管理端PID4182未变、Agent列表仍空。当前源码与验收证据在 `.context/task-history-20261105/`（忽略），包括 `live-history-validation.json`、`native-connection.json`、`installed-artifact.json`、`desktop-result-after-restart.ax.txt`、`final-readonly-audit.json`。48项插件测试、4项服务端离线边界测试、编译/打包和diff检查通过。未改Harness源码、未提交推送；Windows与新模型执行轮次未验收。

## 面试 Skill 新版部署与真实交互（2026-11-05，已完成限定验收）

用户补充测试机可用认证，并明确允许仅独立 `agentos_mvp` 库新增最多2个会话、4次Agent运行的虚构资料测试记录。原SSH认证阻点已解除，本机7777/7778回环转发已恢复；认证信息未写入代码或回执。此授权额度已用完，不得据此继续新增测试运行，后续写库按新任务授权判断。

当前面试Skill发布版为 `20261105.1`，7文件（6文件相较20261028.1改变），文件哈希清单SHA-256 `4dee148a52d056544814a3efdb11b12419a5b26ead668c414c4cb595335bce86`。本机原Skill未改；服务器实际Agno **3.1.10** 已加载并真实读取该版本。目录 `/home/jax/agent-os-poc/mvp/private-skills/releases/20261105.1/java-interview-assessment/`，文件0400、目录0500。清单 `config/interview-release.json` 为 `published`、`jax-mvp-only`、`validation_status=passed-text-interaction`；仅现有单人测试范围，不是全公司生产发布。

真实验证使用原公司模型 `gpt-6.1-sol`：两题样卷v1 → 同会话修改Q1.3为v1.1 → 当前Codex阅读结果并整理本地意见，通过真实公司Host Gateway回传，在同会话修改Q2.2为v1.2。三次成功运行依次为 `94b55dfd-5dfb-4d7e-aed4-7ee52ac7d162`、`6dd35e66-8d80-4c1f-b186-2155a519b32a`、`1b0dea79-94ab-4e33-975e-9aa29e90f2c1`，会话均为 `interview-53063227a3da4306bc7c35f46935ff92`。Q1五行、Q2.2评分单元格与原版一致；Host结果正文SHA与数据库最后assistant正文一致，保留 `byok_allowed`。本轮没有通过日常桌面的个人模型执行本地轮次，不能把Host验证称为桌面混合对话完整验收。

首轮五题请求 `e087fe65-730e-4b1d-9906-1ef93bd89602` 在另一会话 `interview-a86fb53875b9429cb2d8cc2cd6b87791` 超时；实际已读取Skill、两份参考与模板，失败在后续模型请求。模型API超时90→180秒、面试整轮140→270秒后，缩为两题完整格式样卷通过；未重新验证五题或默认完整长卷性能。发现Agno聚合content含工具前过程说明，出口已改为只导出最后assistant业务正文；存量Run纯函数回放及后两次真实响应通过。

部署基于服务器实时源码，备份在 `/home/jax/agent-os-poc/backups/interview-refresh-20261105-043025/`，含原清单、三个适配文件及最终验收回执。员工入口关闭 `auto_provision_dbs`，PostgresDb关闭 `create_schema` 后重启；未执行DDL、初始化或迁移。数据库会话36→38、运行40→44，仍16张表，恰好新增2会话/4运行（3成功、1超时）。管理端PID4182未变，Agent列表仍空；原已清理演示Agent未恢复。回退业务版本时必须保留上述关闭自动建表设置，不能直接整体恢复旧common/employee。

证据在 `.context/interview-refresh-20261105/`，包括 `final-validation-receipt.json`、`final-audit.json`、三轮业务输出与比对结果；最新适配快照也在该忽略目录，不以旧归档替代服务器实况。详细步骤及边界见 `deploy/agent-os-mvp/README.md` 和 `TEST_LOG.md`。本轮未升级日常桌面Bundle、未注入桌面环境令牌、未改Harness源码；桌面仍需单独联调。SSH转发为当前本机临时连接，未新增存口令的自动启动服务。

## 客户端插件保留与显示复核（2026-11-05，连接修复前的观测）

用户反馈插件似乎被清理。已确认独立插件仓库、未提交源码及安装包均仍在；最新混合版本 `1.0.20261102205632` 的 SHA-256 仍为 `a35eb7cc2d08c5a898ab9b1b562332cbadad2dedf33215d64fd9e4f276d3cf34`。

实时官方 macOS 客户端仍为 `0.2.1-rc.5`。原生插件页显示已安装并启用 `@maipro/company-bundle@1.0.20261102183653`，Host/UI 两个组件均运行中，来源为对应本地 tgz。用户当时处于官方插件管理页，并非卸载；已通过“公司界面”入口切回公司工作台，实际界面显示正常。当前公司服务显示“公司服务未配置”。没有重装、升级、卸载或修改凭据，桌面尚未安装混合对话候选版。上次聊天最终回复的安装包链接误写成占位符，本次应补充实际绝对路径。

## 客户端同一对话逐轮本地/云端（2026-11-02，功能候选）

用户明确选择“同一条对话逐轮选择本地/云端”，已在独立插件仓库实现。工作台共用时间线和输入框，每轮保留原问题、执行位置、结果与引用；各对话独立保留草稿、能力、执行位置和工作区，云端历史回看定位完整混合对话。本地使用 Harness 公开 Session create/retain/prompt/eventSource/cancel，复用模型、工具及权限；详情窗口使用原生 Modal 和 conversation，不复制模型循环或改 Harness。原生详情/侧栏的后续本地轮次也回填对应时间线；跨端新结果接续通过协作输入框。

面试按能力复用已确认的 Agno session_id，并传回上次成功云端结果之后的新增本地交付；制度问答接口仍无服务端历史，客户端显式携带已完成结果。Host 保留 export_policy，仅 byok_allowed 的 answer 正文能在用户提交本地轮次时进入个人模型；display_only、未知策略、诊断 JSON 不允许。超长拒绝发送，未知回执/超时不自动重发；云端停止等待不代表服务端停止，本地停止走原生取消。

候选包：`/Users/zhulinfeng/Documents/GitSpace/ai-workspace-client-plugins/artifacts/maipro-company-bundle-1.0.20261102205632.tgz`，SHA-256 `a35eb7cc2d08c5a898ab9b1b562332cbadad2dedf33215d64fd9e4f276d3cf34`。41项测试、生成/编译、打包、frozen install、干净 SDK 绑定与 diff 检查通过。最终 tgz 在原版 npm Harness rc.2 的隔离 DSH_HOME 安装后，合成 MCP → 假本地模型 → 同一云端面试会话的三轮闭环通过，请求核对证明双向交接；导出阻断、对话技能与草稿恢复、原生模型实际选择和权限菜单、公司/官方切换、云端历史打开3轮、375px无横向溢出、亮暗主题通过。四个主要编译文件与安装及 tgz 一致。

证据在插件仓库 `.context/hybrid-20261102/` 与 `output/playwright/hybrid-final-*.png`，实现和边界见 `docs/local-cloud-review.md`、`docs/verification.md`。临时服务和测试浏览器验收后关闭，隔离 profile 的假模型配置恢复。未升级员工日常桌面、未调用真实公司服务或个人模型、未写数据库、未改私有 Skill 或 Harness、未 commit/push。正式 macOS rc.5/Windows 新功能、真实审批工具调用与真实模型待验收。统一时间线、草稿和两端映射仍仅在窗口内存，刷新/重启会清空；原生本地会话自身由 Harness 保存。

## 本地与云端混合体验检查（2026-11-02，前次分析）

用户指出本地/云端割裂，要求体验并结合 AgnoOS 分析。已用插件 `1.0.20261102183653`、原版 npm Harness rc.2 和本机合成 MCP 复现：云端交付面试题后点击“本地会话”，原生输入框为空，结果未交接。根因是 `openLocal` 仅切页、两端会话无关联、Host 丢弃 `export_policy`；不是 Agno 限制本地不能追问。

核对本地 Agno 源码与归档部署：面试工具复用 `session_id` 并开启最近3轮历史，制度问答每次新 UUID 且不带历史；两个演示导出标记 `byok_allowed`。建议以统一任务对话串起 Harness 本地会话和 Agno 云端会话，按轮次执行，通过获准的交付结果/本地新增结论交接上下文；完整协同优先复用 Harness 原生工具链，不复制模型循环。

检查报告在插件仓库 `docs/local-cloud-review.md`，体验证据在 `.context/mixed-tasks-20261102/`。本轮仅分析与复现，未改执行链路、未生成新包、未访问真实公司服务或个人模型、未写数据库。初次分析后用户明确选择“同一对话逐轮选择”，后续实现与验证见上节。

## 客户端侧栏字号修正（2026-11-02）

用户提供新版公司界面截图，指出左侧字体尤其“工作区”不协调。实测公司“工作区”为16px、导航13px，官方均14px；公司侧栏漏了原生容器字号及缩进变量。已在公司插件恢复14px基准、导航22px行高、分组20px行高与原生12px内边距，补齐工作区布局变量和折叠按钮空间。浏览器验证标题 x=16px、工作区名称 x=42px，与官方一致；主内容区字号未改。

最新候选包 `artifacts/maipro-company-bundle-1.0.20261102183653.tgz`，SHA-256 `694756d13f932debc022a2d4745c2f0ca926451f89e66279f25b8521bb846c60`。28项测试、编译、打包、原版npm rc.2隔离Web安装与字号/缩进/折叠验证通过；最终UI/client.js与安装、编译和tgz一致。rc.5原生侧栏12px间距已读提取文件核对。本轮没有更改员工日常桌面安装，也未再次读取其已安装包版本，实际版本以后续实时核查为准。未改Harness源码、服务器或数据库，未提交推送。详细证据见插件仓库 `docs/verification.md` 与 `.context/sidebar-type-20261102/`。

## 客户端 UI 参考适配（2026-11-02）

用户提供 `git@github.com:zeno-sh/AmazonAIWorkspaceUI.git` 作为 UI 参考，已克隆至同名本地目录，参考提交 `2bd4101ed92984bc672bff66052b3d028536af94`。该代码为 React 19/Tailwind 的交互原型，任务进度/日志、SSO、节点、文件回传为模拟；设置没有连接原生配置。参考仓库没有修改。

公司适配仍统一在 `/Users/zhulinfeng/Documents/GitSpace/ai-workspace-client-plugins`：侧栏品牌区、居中输入区、技能发现/固定、任务搜索/状态筛选、网关观测、亮暗主题和窄窗口抽屉。原生会话、工作区、设置、模型继续复用；修复公司/官方切换导致草稿、固定技能和筛选重置。当前仍只有两个测试能力，不代表已接入电商业务、SSO、动态发布或文件回传。

最新本地候选制品 `artifacts/maipro-company-bundle-1.0.20261102182626.tgz`，SHA-256 `c77866e23900ad427120e0fde9d469a16bb147747a064e8797ad8eacad676b99`。28 项测试、编译、打包及原版 npm Harness rc.2 隔离 Web 安装/升级通过；本机合成 MCP、结果、续写、任务筛选、原生设置、界面切换、375px 抽屉焦点/键盘及状态保留均已验证，四个主要 JS 制品与隔离安装一致。检查与验证记录在插件仓库 `docs/figma-ui-review.md`、`docs/verification.md`。

**本次未更新员工当前桌面安装**，其仍为下节 `1.0.20261102152214`；新 UI 的正式 macOS/Windows 验收尚未做。保留当前未提交的 rc.5/无令牌修改，未 commit/push、未改 Harness 源码、服务器、数据库或私有 Skill。

## 客户端安装最新修复（2026-11-02）

本节优先于下文 rc.3 状态。当前员工官方客户端为 `/Applications/DeepSeek Harness.app` 的 `0.2.1-rc.5`。旧包 `1.0.20261029185135` 未声明 rc.5，安装被拒绝。公司插件仓库已生成并在用户当前 desktop profile 原生安装、启用 `1.0.20261102152214`；Host/UI 均显示运行中，公司→官方→公司切换通过，安装后的编译文件与最终 tgz 一致。最终包 `artifacts/maipro-company-bundle-1.0.20261102152214.tgz`，SHA-256 `687328ce8bde768f554dc7316e5c98e09fd6e90b8f482de147b4246e1c65de19`；旧包及中间包已移入 `artifacts/archive/`。失败任务须“返回编辑”替换新包路径，不能只点“重试”。

本次还修复缺少公司令牌导致 Host 启用失败：现在正常加载并显示“公司服务未配置”，任务返回配置提示且不发送未认证请求。令牌仍由 Host 环境变量注入，配置后重启；当前未设置公司令牌，未做真实服务联调。23 项测试、编译、SDK 绑定及制品校验通过，详细证据在公司仓库 `docs/verification.md`。Harness 源码保持干净；服务器、数据库和私有 Skill 未修改。Windows、rc.5 重启及完整升级回退未验收。

## 客户端当前状态：原版独立插件（2026-10-29）

本节替代下文旧布局补丁、迁移初版和开发壳的历史状态。公司 UI、Host、契约及 Bundle 统一在 `/Users/zhulinfeng/Documents/GitSpace/ai-workspace-client-plugins` 维护；当前交付分支 `refactor/20261029_company-ui-plugin_jax`，功能代码提交 `8600637`，rc.3兼容与自动版本脚本修复提交 `c8b76c2` 已推送；当前插件版本 `1.0.20261029185135`，采用北京时间的 `1.0.YYYYMMDDHHmmss`，不修改 Harness 源码。

- Harness 的旧14文件扩展点补丁已核对归档并撤回；`shiteng/develop` 保持原版提交 `f3803c96974ad4a94195fb97e5c637e9c2a3afe3`，工作区干净。插件仓库也删除旧源码补丁，不能再应用历史 `shell.header` / `sidebar.navigation` 补丁。
- 公司插件自行提供 root、导航及布局服务，沿用公开槽位承载原生会话、工作区、设置和工具；原生启动审计后，通过公开 Loader 生命周期切换原生布局/侧栏提供者，禁用、卸载、HMR及失败时恢复。
- 原版 npm CLI 0.2.1-rc.2 的全新隔离 Web 配置验证通过；原版源码0.2.2-alpha.2的隔离 macOS ARM64 Electron 开发壳通过原生插件管理安装、启用、卸载恢复和最终制品重装。设置、模型入口、双向切换及本机合成 MCP 任务通过；21项测试通过。开发壳不等于正式签名安装包，Windows、正式分发及跨版本升级/回退仍待验收。
- 当前制品 `artifacts/maipro-company-bundle-1.0.20261029185135.tgz`，SHA-256 `80e8db363799f4d51c73f4aadf0a52adcd415a981b2b92713296ae5ac6ec1dd6`。桌面在原生插件管理页填 tgz 绝对路径并启用；desktop profile 由 Electron 管理，外部 CLI 不可修改。Web 可使用 `dsh plugin --profile web add <tgz>`。
- 2026-10-29安装失败根因：员工实际安装官方 DSH `0.2.1-rc.3`，旧包只声明 rc.2/alpha.2。已补充精确 rc.3 兼容，并在 `/Applications/DeepSeek Harness.app` 的隔离 Home/userData 验证时间戳版安装、启用、原生设置、合成 MCP 任务和进程重启；原客户端安装目录、源码、员工默认配置和服务器未修改。21项测试通过。新版 `pnpm pack:bundle` 自动同步所有公司包版本、执行 verify 后打包，避免同版本覆盖缓存；发布前检查内嵌包 engines 一致。本地证据 `.context/rc3-compat-20261029/`。
- 开发入口与实际证据看公司仓库 README、`docs/development.md`、`docs/verification.md`、`fixtures/harness/compatibility.json`。SDK绑定改为要求原版源码干净。源码、SDK路径、日志和凭据不混入 Bundle；本地证据在忽略目录 `.context/stock-dsh-20261029/`。
- 本次只用本机合成 MCP 和令牌测试，没有访问或修改生产服务、数据库、私有 Skill 仓库及原有桌面配置。真实公司业务仍需单独联调；ERP、动态授权目录、持久任务和凭据库尚未实现。旧桌面进程不会自动更新为新 Bundle。

## 客户端开发历史（2026-10-28）

已按用户要求使用 3 个 GPT-6.1 Terra 子任务，在 `/Users/zhulinfeng/Documents/GitSpace/deepseek-harness` 的 `shiteng/develop` 实现可选公司工作台。新增 `packages/host/company-skills` 与 `packages/client/ui-company-workspace`，通过 `apps/web/company-workspace.patch.yml` 启用；没有修改 Agno 服务器部署配置，也未提交或推送代码。

- macOS ARM64：独立 Node 24.22.1、pnpm 11.28.5，隔离 DSH Home / Electron userData；`build:artifacts`、Host/Client `build:check`、4 项 Host 测试、6 项组件测试和 1 项真实 Gateway/Loader/HMR 测试通过。
- Web 真实完成规则问答、虚构 Java 面试出题、自动沿用服务端会话修订 Q1 标题；Electron 真实窗口完成规则问答。公司能力未配置个人模型 Key。桌面首次可点“添加 API Key→稍后配置”；开发启动注册了 `dsh://` 默认处理程序。
- 令牌仅由 Host 环境变量读取，页面只读配置变量名；固定两个测试工具适配，不是通用发布目录。结果独立展示，支持 Markdown、历史选择和面试续写，不注册到个人模型工具或会话上下文。
- 任务状态和历史仅在 Host / 窗口内存，重启、刷新或淘汰后不恢复。取消只停止等待，远端可能继续；ERP、多员工权限、动态目录、上传下载、发布后台、Windows、本地浏览器/桌面自动化和正式安装包未完成验收。当前为 M0/macOS 与 M2/文本闭环部分完成，不是生产版或双平台完整交付。
- 飞书《05.实施计划与验证记录》已更新至修订14，主文档当前进度更新至修订80；新增证据和阶段结论回读通过，回执在 Agno `.context/client-mvp-20261028/`。
- 启动方法见客户端包 `README.zh.md`；脱敏截图、界面回读与 `verification.json` 在该仓库 `.context/company-mvp/`（本地忽略）。本次运行环境和日志在 `/tmp/dsh-mvp-runtime/`，日志可能含本地访问 token，不要打印；实际公司 MCP token 从现有 Codex 单一连接配置读入子进程环境，没有写进仓库。

## 沟通与工作原则

- Git 分支以用户指定的[团队规范](https://ncn2eiwq6lph.feishu.cn/wiki/IhnZw3RFci1B0ukpoXzcD2i5nPG)为准：`<type>/yyyyMMdd_feature-name_owner`，type 为 feature/bugfix/hotfix/refactor/chore/docs；仅小写英文、数字、连字符、下划线和一个斜杠，不另用 codex 前缀。日期与功能简称原则上关联禅道迭代，负责人用团队英文名/拼音；缺信息先确认。2026-10-29用户明确允许本次直接按功能名称命名，使用 company-ui-plugin、仓库身份 jax。

- 始终用简体中文，统一采用专业、客观、简洁的公司服务口吻，不使用固定个人昵称。用户已明确取消此前的固定昵称开头约定；后续接入ERP身份认证时，按认证信息中的用户姓名称呼，尚未获取认证姓名时使用中性表达，不猜测。
- 当前开发协作回复仍如实说明模型名称及修订版本；环境未提供修订版本时明确说明，不能猜测。此为开发协作约定，不自动作为面向员工的业务回复模板。
- 用户偏好简单、可验证的小步测试。意图明确就执行，避免反复申请同一授权；缺少真实业务必填输入时先询问，不编造。
- 技术文档采用金字塔结构：结论先行、论据支撑、关键图示；言简意赅，删除重复解释和过时方案，主文档只保留决策与边界，接口等实现细节放子文档。
- 展示实际工具调用、运行记录和产物，不能把演示脚本说成真实业务已打通。新增一个 Skill 不必新增 Agent、容器镜像或专属常驻进程。
- 密码、令牌和模型密钥不写入本记忆、仓库或聊天输出。凭据位置见下文，需要认证时使用已授权的安全方式。
- 数据库写入按 AGENTS.md 和当前会话授权执行。历史授权限独立 MVP 测试库、其初始化迁移及明确的测试，不涉及现有 MySQL；不能把记忆视为对新 SQL 或扩大范围的授权。

## 已确认需求

1. 员工通过 Codex 等现有客户端提需求。普通任务可在本机完成并使用员工自选模型；企业任务委托公司服务。
2. 公司私有 Skill 的说明、脚本、参考资料和业务凭据保留在服务器，员工调用能力，不下载私有源码或拿到公司密钥。
3. 服务端 Agent 使用公司批准的模型、业务工具和必要的执行沙箱；MCP/API 是员工使用企业能力的入口。
4. 支持连续业务交互：提出任务、补充资料或确认选项、生成产物、提出修改、获取新版并保留记录。
5. 管理员统一发布、更新、授权和停用 Skill。最近明确希望“上传 Skill → 选择运行环境与凭据引用 → 绑定 Agent → 测试 → 发布”，普通变更不应每次改代码或重建镜像。
6. 一个 Agent 可以绑定多个 Skill；可按业务职责划分 Agent，不按员工永久分配进程。未来需隔离用户、会话、任务、文件和业务权限。
7. 员工可见结果与可进入员工模型的结果是两个出口。原方案包含独立企业结果展示通道；当前 MCP 返回的业务结果标记 byok_allowed，会进入员工模型上下文，尚未实现 display_only 通道。
8. 员工业务回复采用公司服务口吻，取消固定测试者昵称。后续通过ERP身份认证取得当前用户姓名并用于称呼；当前固定身份 `mvp-jax` 仅为历史测试实现，不能替代ERP认证身份，也不能把ERP对接说成已经完成。
9. 最新客户端需求：新增公司桌面客户端，页面需要自定义；连接公司服务端，展示公司发布的Skill供员工选择执行，查看结果并继续修改，完成业务闭环。用户已确认第一版同时支持Windows和macOS，并同时纳入公司Skill、员工自选模型与本地普通任务；本地任务需支持文件读写、命令执行、浏览器和桌面软件操作。沿用私有Skill源码和凭据留在服务端的边界，客户端展示经授权的能力说明及输入要求。已有Harness源码仓库，现已新增公司功能插件，开发版状态见上文；原有Codex/MCP入口仍保留。
10. 用户已明确选定DeepSeek Harness开源客户端进行二次开发，沿用Electron、React/TypeScript与插件化运行时，增加公司界面和Agno连接插件；此前Tauri+Vue仅为早期建议，已由此次选型替代。本地仓库 `/Users/zhulinfeng/Documents/GitSpace/deepseek-harness`，用户分支 `shiteng/develop`，核对提交 `f3803c96974ad4a94195fb97e5c637e9c2a3afe3`，origin为 `git@github.com:zeno-sh/deepseek-harness.git`。工具链声明Node >=24.9.0、pnpm@11.28.5，桌面包版本0.2.2-alpha.2。必须注意[官方Computer Use组件](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/cua-bundle/README.md)仍为实验性、原生实现仅支持macOS，Windows支持开发中；Cua Driver适配器同样需要实际验证。Harness整体处于预稳定阶段，能力核查阶段仅检查源码；随后客户端开发版的实际构建、启动和测试状态见上文，本地自动化仍未验收。
11. 已按用户授权通过飞书CLI在《00.AI运营工作台》下创建子文档：[01.企业AI桌面客户端与私有Skill平台技术设计（DeepSeek Harness + Agno）](https://ncn2eiwq6lph.feishu.cn/wiki/JjcJwqAeliqo5lkGGb9cIp2NnGm)，docx对象 `HpMJd2wZnoEVfhxaoyycluCUnUd`。包含13章、组件职责、父方案差异、拟定产品接口、结果出口、ERP、发布与双平台验收；父文档正文逐字比对未变，修订号因关联操作从67变为68。子文档正文回读核验通过，首次核验修订15。本地写入源、回执与校验保存在 `.context/client-technical-design-20261028/`；下一步按文档M0启动客户端基线验证，不重建已清理的MVP演示代码。

飞书主文档：[00.AI运营工作台](https://ncn2eiwq6lph.feishu.cn/wiki/N27bwZNnvioVckkQZOzcUlhQnrc)，文档 ID `MlXhdTej8otjZZxiNdCcSgKYnob`。2026-10-28按用户要求将旧方案更新为Harness客户端＋Agno服务端，正文从修订68精简重写至72，包含5节、3张简表及2张保留原token并更新的画板；删除双端Agno、本机Python、腾讯沙箱优先和系统待定等过时设计，接口细节引用上述子文档。正文回读一致；旧稿、写入源与回执位于 `.context/main-design-refresh-20261028/`。需要读取飞书时使用 `lark-cli`，先读其内置 `lark-doc` 及对应引用；本记忆不授权后续修改飞书。

**文档体系最新状态（2026-10-28）：** 按用户要求完善为主文档＋5篇专题。主文档修订78已提供完整导航；原技术设计链接不变，正文重构为《系统技术方案》，修订26，8节，补齐接口、状态、幂等、异常、发布及存储契约。用户随后完成 `wiki:node:update` 授权，原文档已正式重命名为“04.系统技术方案”；通过飞书页面将其排在03之后，CLI复查5篇同级节点依次为01—05，链接与正文不变。主文导航已同步，修订79。新增专题：
- [01.技术调研与选型决策](https://ncn2eiwq6lph.feishu.cn/wiki/EmqFwUwj0iovxUkZWvKcd3v8nIb)：需求R1–R7、候选取舍、决策与重新评估条件。
- [02.Agno与AgentOS能力核查](https://ncn2eiwq6lph.feishu.cn/wiki/WfXvwkM1oijBKbkFglscXPKLnag)：固定源码、原生能力、宿主脚本/队列重跑等限制及项目缺口。
- [03.DeepSeek Harness能力核查](https://ncn2eiwq6lph.feishu.cn/wiki/BIpWwDjJpioCyrkejo8cos3GnHh)：插件、模型、凭据、MCP、平台工具与发布限制。补充核实原生macOS CUA辅助程序的安装包分发、签名和权限归属仍有上游待完成项，不能仅盯Windows风险。
- [05.实施计划与验证记录](https://ncn2eiwq6lph.feishu.cn/wiki/Ct6mw4OhliScIMkeJWLc7kv6nfd)：历史证据H1–H6、M0–M5、需求对应验收T01–T12及待决策输入；未执行的测试未标通过。

五篇专题正文回读与写入源一致，主文导航和3张原画板token均核对保留。源稿、旧稿、回执及验证记录位于 `.context/docset-20261028/`。文档整理阶段仅做源码只读核查；后续客户端开发验收状态见上文，服务器部署配置未改变。后续事实、方案、测试结果分别维护对应专题，避免在总览重复实现细节。

原方案曾考虑自研员工客户端与腾讯沙箱。当前验证阶段采用现成 Codex、内网虚机和 DockerSandbox，这是 MVP 实现调整。Agno、Docker 和控制台均为实现手段，真实企业能力调用闭环仍是目标。

## 当前架构

```text
Jax 电脑
├─ Codex → SSH 转发 localhost:7778/mcp → 员工 MCP 服务
│                                      ├─ ask_private_rules
│                                      └─ generate_interview_questions
└─ 浏览器 os.agno.com → SSH 转发 localhost:7777 → 管理 AgentOS
                                                   ├─ 私有规则问答 MVP
                                                   ├─ Java 面试出题
                                                   ├─ Docker 沙箱演示
                                                   └─ Studio MVP 验证 Agent

192.168.1.166
├─ 两个 AgentOS Python API 进程 → 公司 OpenAI 兼容中转
├─ PostgreSQL + pgvector：系统 Docker 容器
├─ 沙箱演示 Agent → 本地 Unix socket → 受控执行进程
│                                      └─ Agno DockerSandbox → Docker 任务容器
├─ 私有 Skill：服务器文件目录
└─ 会话存 PG；演示产物和沙箱操作记录存服务器数据目录
```

- `os.agno.com` 是管理界面，浏览器直接连接自己的 Runtime；Agent、数据库和执行环境在内网服务器。
- 顶部“Local AgentOS”是连接名称。localhost 是 Jax 电脑上的 SSH 转发入口，不表示服务部署在 Mac。
- 数据库容器和任务沙箱是不同容器。普通模型 Agent 运行在 API 进程中，演示脚本在沙箱中执行。

## 环境与入口

| 项目 | 当前值 |
|---|---|
| 本地仓库 | `/Users/zhulinfeng/Documents/GitSpace/agno` |
| 本地部署资料 | `deploy/agent-os-mvp/` 仅保留Markdown；源码已移入 `.context/cleanup-20261028/mvp-deployment-full.zip` |
| 虚机 | `192.168.1.166`，SSH 用户 `jax`，端口 **22**；不能套用线上服务器的235端口规则 |
| 虚机环境 | CentOS Stream 9 ARM64，4 vCPU，约6GB内存 |
| 服务根目录 | `/home/jax/agent-os-poc`，部署源码在其 `mvp/` |
| Python | `.venv-mvp/bin/python`，Python 3.12.16；底层独立运行时在 `.python/` |
| Agno | 3.1.10；PoC框架源码来自提交 `ffe47567920e5a5c5d5d416c2b366f8c32c62f31`，未修改框架实现 |
| Docker | 宝塔安装的系统 Docker 26.1.4，Compose 2.28.1 |
| 管理 API | 虚机 `127.0.0.1:7777`，用户服务 `agno-mvp-admin.service` |
| 员工 MCP | 虚机 `127.0.0.1:7778/mcp`，用户服务 `agno-mvp-employee.service` |
| 模型 | 公司中转 Responses API，`gpt-6.1-sol`；原gpt-5.5曾被中转拒绝，模型变更由用户确认 |
| 模型和应用配置 | 虚机 `config/mvp.json`，0600，含模型及MCP凭据和数据库连接；不得打印内容 |
| Codex MCP | Mac `~/.codex/config.toml` 的 `company_private_rules`，已允许上述两个业务工具；正常审批策略未改变 |

员工 MCP 当前使用一个静态令牌、固定测试身份 `mvp-jax`。对外只放行业务MCP接口，配置、Registry、会话和其他管理REST路径为404。管理端只经操作者回环隧道访问，尚未配置正式多用户JWT入口。SSH隧道曾断开，排障先区分隧道故障与虚机服务故障。

公司模型端点和Header保留在服务器配置中，使用 `store=False`。这不等于第三方中转保证不留日志。未配置正式内网HTTPS、SSO和多员工权限。不要将测试令牌分发给全体员工或开放管理端口。

## 数据库与备份

- PostgreSQL 18.6、pgvector扩展0.8.7，容器 `agentos-mvp-postgres`，Compose项目 `agentos-mvp`。配置文件 `mvp/compose.postgres.yaml`。
- 数据库同时映射服务器 `127.0.0.1:5532` 和内网 `192.168.1.166:5532`；数据库及专用账号 `agentos_mvp`，schema `agentos`。账号非超级用户，无建库或建角色权限。
- 2026-10-28先建立本机5532端口SSH转发，随后用户明确要求用dbx通过内网IP直连，已在服务器Compose中增加内网IP映射，保留回环映射和原隧道。Mac直连PG协议检查、内网地址应用账号认证及SELECT查询通过；dbx用 `192.168.1.166:5532`，不需要隧道，SSL默认prefer即可。密码保留在服务器配置，不写入记忆。
- 端口调整前Compose及数据行数基线保存在 `/home/jax/agent-os-poc/backups/pg-lan-access-20261028-080052/`。仅重建PG容器，原数据卷未变，29个会话、32条运行、组件及配置版本各1条的行数一致；两个API进程未重启，健康及MCP工具发现通过。旧源码归档中的Compose早于此次内网映射变更，恢复时先比对服务器配置。
- 当前Docker数据卷 `agentos-mvp-pgdata` 位于 `/var/lib/docker/volumes/agentos-mvp-pgdata/_data`。迁移已逐表比对16张应用表，记录保留完整，AgentOS和Codex回归通过。
- 原 SQLite `data/mvp.db` 保留。原rootless Podman同名数据卷是另一份数据，保留在用户容器存储目录；旧Quadlet已改名为 `.container.disabled`，不得同时启动抢占5532端口。
- 备份保存在 `backups/before-postgres/`、`backups/before-docker/`，以及 `backups/agentos_mvp-after-docker.dump` 等。旧Podman卷不会自动同步迁移后的新数据，不能无条件直接切回。
- 管理及应用数据库凭据分别在 `config/postgres.env`、`config/postgres-app.json`，不输出内容。没有配置定时备份或高可用；没有修改现有MySQL。
- `setup_postgres.py`、`initialize_docker_database.py`、`migrate_sqlite_to_postgres.py` 及旧Podman配置已包含在上述完整归档中；这些是历史一次性初始化/迁移文件，不得当作日常启动步骤重复运行。

## 已验证的三类能力

### 私有规则问答

- Agent ID `private-rules-agent`，只加载 `mvp/private-skills/demo-expense-rules/`，内容为虚构报销规则。
- MCP工具 `ask_private_rules(question)` 已由真实Codex调用。对外只返回有限判定与固定文案，不返回私有工具消息或规则原文。
- `common.py` 管理此Agent、模型、数据库与Registry；`employee.py` 管理两个员工业务工具、鉴权与出口。

### 原生 DockerSandbox 演示

- Agent ID `docker-sandbox-demo`。服务端通过受控工具调用 Agno 原生 `acreate/aexec/aget/adestroy`，不是只写了直接docker命令。
- 执行进程为系统服务 `agentos-sandbox-demo.service`，Unix socket `/run/agentos-sandbox-demo/worker.sock`。仅该服务进程有Docker补充组；jax未加入docker组，AgentOS进程及任务容器均未挂载Docker socket。
- 镜像 `agentos-sandbox-demo:20261028`，由已有基础镜像和Python离线构建，不包含模型凭据、私有Skill或数据库文件。不是完整Codex/Claude harness运行时镜像。
- 限制：非root、只读根目录、无网络、1CPU、256MiB、64PID、32MiB工作区；最多两个演示容器。每30秒检查过期会话，闲置15分钟后销毁，导出报告保留在 `data/sandbox-demo/`。
- 控制台已完成报告v1生成、同容器修改为v2，另验证销毁及新一代容器重建。没有工作区检查点，容器销毁后不能恢复原工作区。
- 普通Agent通过工具调用沙箱，因此 `/agents` 中 `sandboxed=false` 是预期值。当前框架普通 `Agent(sandbox=...)` 尚不支持；`CodexAgent/ClaudeAgent` 可整套harness进入沙箱，本次没有采用该模式。
- `sandbox_demo.py`、`sandbox_worker.py` 为主要实现；`check_sandbox_demo.py` 为实际环境测试。
- [控制台演示会话](https://os.agno.com/chat?type=agent&id=docker-sandbox-demo&session=59dd0530-3913-4356-b197-e281f8b00ddc)。截图在本机 `.context/native-sandbox-proof/`。

### 面试出题 Skill 发布演练

- 原Skill：`/Users/zhulinfeng/.codex/skills/java-interview-assessment`，原7个文件未修改。
- 发布版 `20261028.1`，服务器目录 `/home/jax/agent-os-poc/mvp/private-skills/releases/20261028.1/java-interview-assessment/`，文件只读。
- 文件清单总hash：`3d2c94806de9a7a6c2caa1b55e322b437ca6b92246d5b25fd0917d1a819ff8a3`。配置回执在服务器 `config/interview-release.json`，stage为published，audience为jax-mvp-only。
- 新增“Java 面试出题”是一个服务端Agent配置，ID `java-interview-agent`；不是新服务器、容器或每名员工的独立进程。它使用公司模型、仅绑定该Skill、只读说明/参考/固定模板，记录存现有PG。
- 这是纯说明Skill，无执行脚本；本次没有新建镜像、安装依赖、增加凭据或数据库表。实现 `interview_agent.py`，员工MCP入口 `generate_interview_questions(request, session_id=None)`。
- 使用虚构简历在控制台生成5题（基础3题、项目2题），每题5点评分、NA空白记录；第二轮只改Q1表述，五行评分锚点与v1逐字一致，没有实际候选人评估。
- 已验证testing状态拒绝员工执行；发布后真实Codex调用成功，并通过MCP继续同一份题单。原报销工具也回归通过。
- 首次Codex曾将可选session_id传空字符串导致校验失败，已兼容null/省略/空字符串作为新任务；继续会话核对固定用户及Agent归属，非法编号拒绝。
- 当前只收文本，不解析PDF、不写Obsidian、不评分或决定录用。新增MCP工具可能需要Codex新开会话或重连才能发现。
- [控制台验收会话](https://os.agno.com/chat?type=agent&id=java-interview-agent&session=4cae1c88-b141-424c-b4b3-4ed0cae39190)。题单、Codex业务结果、发布回执与截图在本机 `.context/interview-release/`；服务器样本在 `data/interview-publish-test/`。
- **这是手工代替后台执行的发布演练，不是已经实现网页上传、绑定和自动发布。** `published` 是当前演练配置状态，不代表已向全公司生产发布，也不等于在Studio点过Publish。

`studio-mvp-agent`（Studio MVP 验证 Agent）曾保存发布为版本1，用于验证配置持久化，未向员工MCP开放。2026-10-28按用户清理控制台测试条目的要求，已通过组件API将其归档，可经restore接口恢复；浏览器下拉列表已确认不再显示，配置版本与历史记录保留。操作前组件与配置备份在本机 `.context/console-cleanup-20261028/`。

控制台清理已完成：用户补充可用SSH登录方式后，备份服务器 `admin.py` 至 `/home/jax/agent-os-poc/backups/console-cleanup-20261028-075331/`，移除3个管理端测试Agent及演示报告预览路由，关闭管理端自动建表，只重启管理服务。`/agents` 返回空列表，浏览器确认无Agent；员工服务PID保持37672，两个MCP业务工具发现及管理接口隔离检查通过，未调用模型。只读查询确认29个会话、32条运行和Studio的1个配置版本仍保留。当前管理端源码及操作元数据存于本机 `.context/console-cleanup-20261028/`；现有MCP和演示执行服务未停用。

## 尚未实现与继续工作的边界

- Skill ZIP上传、格式检查、运行环境选择、凭据引用、Agent绑定、试运行、一键发布/回滚的通用管理员页面及后端，尚未开发。
- 普通说明/模板变更、使用既有依赖的脚本可设计成上传配置即可生效。脚本可按任务传入沙箱，不必每个Skill烘焙镜像；新依赖才需要准备运行环境。此为后续目标，不能说当前已自动实现。
- 真实市场调研尚未完整接入。之前只在容器做过Sorftime采集脚本的零接口调用dry-run，简单HTML测试也不是正式市场报告。
- 市场Skill源在 `/Users/zhulinfeng/Documents/GitSpace/AI-E-commerce/skills/`，存在Sorftime v2、SellerSprite v2及另一套旧版，用户尚未最终确认采用哪套。此前建议优先Sorftime v2，但不得当作已确认。
- 真实采集仍需明确站点、产品/关键词、月份、数据源账号及调用额度；还需CLI运行时、报告渲染依赖、图片能力验证。禁止在缺业务输入时擅自调用付费接口。
- 市场源仓库有用户未提交的领星提醒Skill修改，不碰这些改动；运行产物必须外置，不能写回Skill源码。
- ERP身份认证与认证姓名接入、多员工SSO/RBAC、正式产物鉴权、display_only通道、持久化业务任务队列/中断恢复、审批、完整审计和多机扩容尚未完成。会话存PG不等于任务与工作区能自动恢复。
- 最新工作方向为基于用户 `shiteng/develop` 分支开发Windows和macOS自定义Harness客户端，第一版同时包含公司Skill和完整本地自动化，技术设计已落飞书子文档，下一步M0基线验证。首批正式Skill与ERP接口尚待补齐；视觉稿已采用 Figma Make 的 Amazon AI 运营工作台。当前员工MCP仅开放两个固定工具，通用Skill目录与发布接口尚未实现，不得将现状描述为已具备完整Skill商店。

## Harness 公司桌面布局历史（2026-10-29，已被独立插件替代）

- 客户端仓库 `/Users/zhulinfeng/Documents/GitSpace/deepseek-harness`，分支 `shiteng/develop`。按 Figma Make `zu5vln4NlwUsXwNHXSqdIq` 实现可选公司 UI 插件：通栏顶栏、侧栏导航、工作台、技能广场、云端任务及 MCP 状态。原生 UI 仅新增 `shell.header`、`sidebar.navigation` 扩展点，保留原生工作区、会话、插件管理及设置。
- 顶栏“官方界面”撤回公司顶栏、导航与主题覆盖，侧栏“公司界面”恢复。主题沿用原生服务，设置入口调用原生设置；公司任务结果不注入个人模型。Mac 开发桌面已实际验证双向切换、亮暗主题、原生设置、技能侧栏快捷入口和原生插件管理。
- 当前仍只有两个测试能力；任务和快捷入口为窗口内存状态，最多保留100条任务，刷新或重启丢失；草稿与运行轮询跨页面及布局切换保留。停止等待不等于停止远端执行。ERP、正式动态 Skill 发布、持久任务中心与 Windows 打包尚未验收。
- 布局联调最初因虚机关机而返回服务不可用，界面正确展示失败并保留输入。用户开机后复核两个 API 服务均 active、管理健康200；恢复本机7777/7778原有回环SSH转发，桌面真实规则问答完成，任务 `a960f33d-f149-4eb8-a90f-0184830f5d89`，返回普通审核结论，顶栏显示最近连接成功。当前恢复证据为客户端 `.context/company-layout-20261029/cloud-restored.png`；没有重启服务、修改服务器配置或执行数据库SQL。客户端修改尚未提交。91项针对性测试、最新制品插件加载测试、8项构建门禁与Host/Client校验通过；槽位目录、客户端包结构及国际化检查通过。实现与使用边界见客户端包 `packages/client/ui-company-workspace/README.zh.md`，本地截图在客户端 `.context/company-layout-20261029/`。

- 同日按实际体验问题迭代：撤回公司布局下的原生 `shell.leading` 控件以修复折叠重叠；公司返回入口仅在官方布局出现，删除本地能力重复卡片；侧栏统一为实色，圆角、焦点沿用原生变量。工作台成对展示原始问题与结果，元数据默认折叠；历史以摘要和客户端提交时间标识，草稿按技能保留，任务接受后只清除已提交文本。42项针对性回归、36项修复后的样式/侧栏测试、2项真实浏览器原生侧栏/设置测试、8项构建及2项Host/Client校验通过；完整GUI初跑有10项失败，相关7文件已修复并单独全过，未再全量重跑；完整Web因缺浏览器中止，补齐后只跑上述2项。桌面真实云端任务 `94f41b66-0105-41cc-b6e9-c8cbf12c4618` 完成，Cmd+Enter、问题与结果、历史回看、详情、官方回切及亮暗主题均验收，恢复跟随系统。证据见客户端 `.context/company-layout-20261029/polish-verification.json` 与 `polish-*.png`，未改服务器。

- 2026-10-29已按用户授权创建并初始化 Gitee `zhulf` 下两个私有仓库，本地均在 `/Users/zhulinfeng/Documents/GitSpace/` 下的同名目录，默认分支 main，初始化提交已推送、远程 SHA 核对一致且工作区干净：客户端插件 `https://gitee.com/zhulf/ai-workspace-client-plugins`（`dce367d92f1348cff7a3501d73d7404ed922d468`）；服务端私有 Skill `https://gitee.com/zhulf/ai-workspace-private-skills`（`d6c26012e4814a6edac071ca081c37e625c566cf`）。客户端预留 company-ui、company-host、contracts、company-bundle；Skill 仓库包含草稿模板、清单 v1、JSON Schema 和离线校验工具，skills/ 尚无正式技能。各自 README、AGENTS.md、docs/development.md 已定义开发与发布边界；客户端骨架检查、Skill 模板校验、7项边界测试及草稿/空集合发布门禁通过。
- 同日通过飞书 CLI 在《九、AI工作台》`JjAbwRg2oiDgackOUhIcgXmbn5e` 下创建并回读验证 [01.客户端插件开发规范](https://ncn2eiwq6lph.feishu.cn/wiki/XloWwcKsyiXk1gkNzfqchhlcnDf)（docx `GVTfdPlheos883xXQFDc1tWonUh`）和 [02.私有Skill开发规范](https://ncn2eiwq6lph.feishu.cn/wiki/KktkwMM8fiYIVGkghBGcQdJBnTh)（docx `JXx2dT3y3owXVVxDvQTcL6fEn0g`），与原“00.技术调研”并列，每篇5章、2张表，正文与本地写入源回读一致。源文件、回执及核对证据在 `.context/repository-bootstrap-20261029/`。
- 此次仅初始化，不迁移原 Harness 工作区的 MVP、不改远程地址或服务器部署。源码基线0.2.2-alpha.2与当日查询的公开 CLI0.2.1-rc.2不同；现有 MVP 依赖未提交的 shell.header、sidebar.navigation 槽位补丁，尚不能宣称原版客户端可安装。后续按客户端 M0独立Bundle验证 → M1业务迁移 → M2双平台分发 → M3身份/目录/产物闭环迭代；Skill清单v1为新增仓库约定，尚未集成现有AgentOS自动加载或发布。

## 公司客户端初次迁移历史（2026-10-29，补丁方案已撤回）

- 用户明确本次只迁公司 UI 与客户端连接插件，不迁私有 Skill。公司插件源码、测试及 Bundle 已从 Harness 移入 `/Users/zhulinfeng/Documents/GitSpace/ai-workspace-client-plugins`，提交 `5a44b528c711b4c632917ddc9c5a99a1ec4173bc` 已推送 Gitee main，远程 SHA 一致、工作区干净。后续修改公司 UI 看 `packages/company-ui/src/client/`，Host 看 `packages/company-host/src/`，共享数据类型看 `packages/contracts/src/types.ts`，安装组合看 `packages/company-bundle/`。
- 原 Harness 的两个公司源码目录、公司 overlay、内置依赖和专属编译/检查配置已移除；只剩14个文件的通用布局扩展、文档和回归测试改动，仍未提交/推送。可复现副本在插件仓库 `patches/harness/layout-slots.patch`；在干净基线文件集上应用成功并与当前14文件逐字节核对。不要从旧归档把公司代码恢复回 Harness 形成双份维护。
- 开发命令：Node>=24.9.0 / pnpm11.28.5，先 `pnpm install --frozen-lockfile`，再 `pnpm sdk:prepare -- <Harness目录>`，随后 `pnpm verify`、`pnpm pack:bundle`。当前基线 SDK 为0.2.2-alpha.2 / f3803c96974ad4a94195fb97e5c637e9c2a3afe3，SDK绑定会核对完整通用补丁SHA；SDK链接、分析快照与绝对路径均忽略，不随制品交付。SDK上游工具尚依赖工作区类型所有者，因此本地忽略目录有实际 protocol/brand 分析文件副本，运行时仍复用原生服务。
- 插件完整verify通过18项，原生侧栏/窗口样式34项及槽位目录检查通过。Bundle 0.1.0含48个文件，内嵌公司包及所需许可证，排除了源码、source map、SDK、Skill、凭据及运行数据；已在独立测试DSH_HOME中用Harness自带CLI真实安装、启动Web并在浏览器验证公司/官方双向切换与原生设置。最终页面0个错误，冷启动出现1次generation-delay提示后正常就绪。合成凭据只用于本机验证，没有调用真实公司业务，没有修改原桌面配置或服务器；macOS桌面完整安装/升级/卸载、Windows及原版客户端验收仍pending。原本正在运行的桌面是旧开发制品，不会自动随新仓库源码变化，后续需通过Bundle安装更新。
- 飞书客户端规范已有独立更新，保留现有章节，仅定向更新了公司迁移及SDK开发入口说明，修订20/21写入后回读确认；没有覆盖其他规范内容。状态与验证证据以仓库 `fixtures/harness/compatibility.json` 和 `.context/migration-20261029/verification.json` 为准。私有Skill仓库保持main且干净，服务器、数据库、隧道与已有服务均未改动。
- 迁移前公司源码与原工作区差异备份：`/Users/zhulinfeng/Documents/GitSpace/ai-workspace-client-plugins/.context/migration-20261029/harness-company-source.zip`，SHA-256 `f996fae5e13397c44316554830ff1858aa40d82ec9fcc3fcfe970550306d77d6`。本机忽略归档仅用于恢复，不随Git提交。最终Bundle SHA-256 `9e2ab24d0e19c84cd103871c671cf9909c6719acae57cce3d461cbafc111812b`。

## 新会话执行入口

1. 先读本文件、`deploy/agent-os-mvp/README.md` 和 `TEST_LOG.md`。对应实现已归档，需要查代码时先在独立临时目录解包核对。
2. 先 `git status --short`。截至本次清理，未提交内容只包含Markdown文档；MVP代码、配置和回归脚本均已归档，未commit/push/PR。不要把只剩文档的本地目录通过带删除选项的同步命令覆盖服务器部署目录。
3. 按新任务核查服务、隧道与版本即可，不重复初始化数据库或重新跑所有历史模型测试。现有 `.context/` 是本机gitignored归档及佐证目录，保存源码压缩包，但不作为唯一记忆入口。恢复本地源码不等于授权部署或执行数据库脚本。
4. 虚机常用只读检查：`systemctl --user is-active agno-mvp-admin agno-mvp-employee`、`curl http://127.0.0.1:7777/health`；Docker检查需要受控管理权限。没有理由时不要改变用户组或开放socket。
5. 虚机此前难以直连Docker Hub，已缓存ARM64镜像，存在本机离线下载脚本；先判断当前网络，不无故重装软件。
6. 本次仅在部署目录做过针对性Ruff/格式/编译与集成验证，没有推送或PR。若今后要推送/PR，仍须按仓库规则运行完整format/validate。

本文件只保存需求、现状和继续工作的边界；详细运维与运行编号在 `README.md`、`TEST_LOG.md`。新增事实后维护本文件，避免把后续计划写成已完成。
