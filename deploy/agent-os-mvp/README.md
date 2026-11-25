# 内网 AgentOS MVP

## 架构切换：员工端升级 `/v1/*` 独立云端会话网关（2026-11-25，已部署）

配合客户端独立云端会话插件 `maipro-company-bundle-1.0.20261125145333.tgz`，员工端口 `192.168.1.200:7778` 切换为 `/v1/*` 产品网关（[runtime/v1_gateway.py](runtime/v1_gateway.py)、[runtime/employee.py](runtime/employee.py)），仅开放 `/health` 与 Bearer 鉴权的 `/v1/*`，旧 `/agents`、`/sessions` 返回 404；管理端 `127.0.0.1:7777` 不受影响。`/v1` 会话、轮次、幂等键、SSE 游标与附件元数据落盘于 `/root/agent-os-poc/data/company_v1.db`（SQLite WAL），未改动 PostgreSQL 结构。旧版 `employee.py` 备份在 `/root/agent-os-poc/backups/v1-gateway-20261125/employee.py`；回退时恢复该文件并重启 `agno-mvp-employee.service` 即可。

## 架构切换：MCP 废弃，原生 Agent 运行 API（2026-11-17，已被 11-25 架构取代）

技能升级为真 Agent（`Agent(model=relay_model, tools=[沙箱脚本], db=db)`），员工端白名单 `/agents`+`/sessions`+`/health`，MCP 已下线（404）。客户端走原生 API：`GET /agents` 技能发现（含工具参数 schema）、`POST /agents/{id}/runs`（multipart form，`stream=true` SSE：RunStarted/RunContent 增量/RunCompleted）、`GET /sessions?component_id=&user_id=` + `GET /agents/{id}/runs?session_id=` 历史、`POST /runs/{id}/cancel` 取消。备份 `backups/*-before-agents-20261117-114523.py`。回退：恢复备份并重启员工服务，客户端装回旧 bundle。配套客户端 `maipro-company-bundle-1.0.20261117120531.tgz`。

## 结构化技能自由文本 note（2026-11-16，已被 11-17 架构取代）

两个结构化工具 `calculate` / `query_earthquakes` 新增可选参数 `note`（≤2000 字符自由文本）。客户端把输入框里的补充说明随参数一起提交；服务端脚本仍只按参数执行（`ScriptModel` 以 `script_fields` 白名单剥离 note 后喂脚本），note 非空时服务层用 `common.py` 的共享中转模型（`relay_model`，glm-5.3）把"脚本结果 + 用户补充要求"组织成最终 answer，LLM 失败自动回退纯脚本结果。`tools/list` 已发布 `note`（非必填），旧客户端不带 note 完全兼容。

已部署至 `192.168.1.200:/root/agent-os-poc/mvp/script_agents.py`（SHA-256 `d4b2fa6c…` 与本地一致），重启 `agno-mvp-employee` 后真实调用验证通过：`expression=12 + note="告诉我计算的过程和原理"` 返回了包含脚本结果、三步计算过程与原理说明的完整回答（run `99ca7b5f`）。回退：恢复 `backups/script_agents-before-note-20261116-191134.py` 并重启员工服务。桌面端需安装 `maipro-company-bundle-1.0.20261116190608.tgz` 或更新版本才会发送 note；旧 bundle 不发 note，对新服务端无影响。

## 当前部署（2026-11-06）

| MCP 工具 | Agent | 必填参数 |
| --- | --- | --- |
| `calculate` | `calculator-agent` | `expression`，1–160 字符的十进制四则表达式 |
| `query_earthquakes` | `http-info-agent` | `latitude` 为 −90 至 90，`longitude` 为 −180 至 180，均为数值 |

员工 MCP 通过 `tools/list` 发布 JSON Schema，客户端依字段的名称、类型、必填和范围渲染表单。Agent 只启动各自固定目录的 Python 脚本，通过标准输入传 JSON。HTTP 脚本使用固定 HTTPS 地址，查询指定点 500 公里内最近 30 天的最新记录。两个员工 Agent 均无 PostgreSQL 持久化，结果在当前客户端运行期可查阅。原历史查询继续以测试身份只读访问。

当前虚机的 `mvp/private-skills/` 只包含 `calculator/` 和 `http-info/`。服务端入口源码在 [runtime/](runtime/)，两项 Skill 及脚本在 [skills/](skills/)。旧 Skill 和切换前的 `admin.py`、`employee.py`、`common.py`、`interview_agent.py` 备份于 `/home/jax/agent-os-poc/backups/structured-skills-20261106-111413/`。员工历史的导出检查通过 `mvp/retired-skills` 读取归档；该目录不注册为员工执行入口。

回退时先停两个用户服务，将当前 Skill 目录移入独立备份，恢复旧 Skill 目录、上述四个 Python 文件及原目录结构，移除新增的 `script_agents.py` 和 `retired-skills` 链接，再重启并核对管理端健康、MCP 工具和旧历史。旧 Skill 根目录恢复后继续保留 `create_schema=False` 与 `auto_provision_dbs=False`。旧部署脚本和完整归档位置见 [PROJECT_MEMORY.md](../../PROJECT_MEMORY.md)。

## 历史桌面连接与只读记录（2026-11-05）

员工MCP现有两个执行工具，以及只读 `list_company_tasks(limit=50, cursor=None)`、`get_company_task(run_id)`。历史查询以固定测试身份 `mvp-jax`、两个业务Agent为范围，使用只读数据库连接；列表返回输入、状态、时间和运行/会话引用，详情仅返回通过现有导出检查的业务正文。不存在记录不可读取，非法游标被拒绝，内部消息、工具内容、Skill与配置不导出。

当前正式macOS Harness0.2.1-rc.5已通过原生界面升级公司Bundle至 **1.0.20261105131154**。Host按操作解析原生凭据引用 `DSH_COMPANY_MCP_TOKEN`，公司连接已配置且重启后保持。云端任务页读取37条服务端记录（35成功/2失败），最新4条为面试验证；打开最新记录可回看v1、v1.1、v1.2，同会话三轮在客户端退出重开后仍可重新读取。

这次只读取已有记录，数据库仍38会话/44运行/16表，未新增Agent运行。服务端源码备份在 `backups/task-history-20261105-050906/`，仅重启员工服务，管理端保持为空。云端记录读取不恢复本地轮次和草稿；本轮没有向个人模型提交请求，仍不能据此宣称完整混合时间线持久化。详细证据见 [TEST_LOG.md](TEST_LOG.md)。

## 历史面试 Skill 部署（2026-11-05）

`java-interview-assessment` 已发布为 **20261105.1**，位于服务器 `mvp/private-skills/releases/20261105.1/java-interview-assessment/`。本机原Skill未修改，7个文件逐一SHA-256一致，服务器文件0400、目录0500。文件哈希清单总SHA-256：`4dee148a52d056544814a3efdb11b12419a5b26ead668c414c4cb595335bce86`。实际运行Agno3.1.10，沿用原 `gpt-6.1-sol` 模型与连接配置。

当前入口仍为 `generate_interview_questions(request, session_id=None)`，绑定 `java-interview-agent`。清单 `config/interview-release.json` 为 `published`、`jax-mvp-only`、`validation_status=passed-text-interaction`，只面向原单人测试令牌。管理端Agent列表继续为空，不在控制台恢复演示Agent。

已用虚构简历验证以下交互：

1. 员工MCP生成两题完整格式样卷v1：每题5个评分点、0/1/2锚点、NA与空白得分，基础/项目60%/40%。
2. 携带返回的同一 `session_id` 修改Q1.3为v1.1；五行评分标准逐单元格保持一致。
3. 当前Codex阅读题单后整理本地意见，经公司插件实际Host Gateway回传，服务端同会话修改Q2.2为v1.2；原评分行保持一致，Host业务正文与持久化运行正文哈希相同。

成功会话为 `interview-53063227a3da4306bc7c35f46935ff92`，三次运行引用及完整检查见 [TEST_LOG.md](TEST_LOG.md)。这证明业务结果可以交给本地分析，再带回原服务端会话；本轮未在日常桌面调用个人本地模型，桌面UI混合轮次仍待实测。

首轮五题请求在读取Skill、参考和模板后遇到模型90秒超时。现已将模型API超时改为180秒、面试整轮改为270秒；两题样卷及后续修订成功，五题和默认完整长卷尚未复验。出口从聚合 `run.content` 改为最后assistant业务正文，避免夹带工具前过程说明；既有凭据、路径与私有原文检查保留。

本次明确授权的测试额度已用完：只在 `agentos_mvp` 新增2个会话、4次Agent运行（3成功、1超时）。未执行DDL、迁移或初始化，员工启动设置为 `auto_provision_dbs=False`、`create_schema=False`。配置/源码备份及最终回执在服务器 `backups/interview-refresh-20261105-043025/`；回退清单和业务代码时须保留关闭自动建表设置。

本机7777/7778回环SSH转发已恢复，仍为当前机器的临时连接；日常桌面Bundle与令牌配置本轮未更改。证据在本地忽略目录 `.context/interview-refresh-20261105/`，不含可提交的凭据。后续任何会写库的验收脚本均须重新核对当前任务授权。

## 历史部署说明

部署目标：`jax@192.168.1.166`，目录 `/home/jax/agent-os-poc`。
核心框架使用本仓库提交 `ffe47567920e5a5c5d5d416c2b366f8c32c62f31`，没有修改框架代码。

## 本版链路

```text
管理员浏览器 os.agno.com ── SSH 转发 localhost:7777 ── 虚机管理 API
员工 Codex ── SSH 转发 localhost:7778/mcp ── MCP 鉴权
                                             │
                                  ask_private_rules
                                             │
                                  服务端 Agent + 私有 Skill
                                             │
                                  OpenAI 中转 Responses API
                                             │
                                  枚举判定 → 固定文案结果
```

两个 Python 服务实际均运行在虚机。`localhost` 是本机 SSH 隧道入口。
SSH 隧道仅供 Jax 单人开发验证，尚未提供面向全体员工的内网 HTTPS 入口。

- 管理端：`127.0.0.1:7777`，供已连接的官方控制台调用，具备 Studio、Registry、会话等接口。
- 员工端：`127.0.0.1:7778/mcp`，需要独立Bearer令牌；两个业务执行工具以及两个按身份筛选的只读历史工具，最新说明见上方章节。
- 员工端阻止管理 REST、WebSocket、历史记录和配置接口；不开放通用 `run_agent`。
- 模型：`gpt-6.1-sol`，使用指定中转及请求头，设置 `store=False`，关闭上一响应 ID 串联。
- 数据库：独立 PostgreSQL 18.6＋pgvector 0.8.7，虚机回环地址 `127.0.0.1:5532`，库和专用账号均为 `agentos_mvp`，AgentOS 表位于 `agentos` schema。未连接现有 MySQL。
- 原 SQLite `/home/jax/agent-os-poc/data/mvp.db` 完整保留；切换时已有11个会话、11条运行记录及 Studio 配置/版本已迁入 PostgreSQL。
- 私有 Skill：`mvp/private-skills/demo-expense-rules/SKILL.md`，仅演示虚构报销规则。
- 规则 Agent 只注册 `get_skill_instructions`。面试出题 Agent 可读取固定版本的说明、参考资料和模板；两者均没有 Skill 脚本执行工具。

## 直接验证

在本机 Codex **新开对话**，确认 `company_private_rules` 已连接，然后输入：

> 调用 company_private_rules 的 ask_private_rules：为工作购买办公用品，人民币300元，需要怎么处理？

第一次使用按客户端提示批准本次工具调用。预期答复：

> 这笔演示申请可进入普通审核流程，仍需人工核验票据。

其他场景：人民币800元办公用品应返回主管审核；未提供完整信息应要求补充；索取 Skill 原文应拒绝。

本机已添加 `~/.codex/config.toml` 中的 `mcp_servers.company_private_rules`，只保存员工令牌。
本次对话的工具列表可能需要新开对话或在 MCP 设置中重连才能更新。
模型密钥仅保存在虚机 `config/mvp.json`，权限 `0600`；没有放进代码。

管理控制台 Chat 中选择“私有规则问答 MVP”，可以查看结构化判定及工具调用。
Studio 中的“Studio MVP 验证 Agent”是另一个已保存、发布为版本1的配置示例；它没有私有 Skill，未向员工 MCP 发布。
Studio Registry 已提供模型和测试库，可在网页创建新的普通 Agent。私有 Skill 仍由服务端代码配置。

## 运维

虚机服务：

```bash
systemctl --user status agno-mvp-admin agno-mvp-employee
sudo docker compose -f /home/jax/agent-os-poc/mvp/compose.postgres.yaml ps
systemctl --user restart agno-mvp-admin agno-mvp-employee
cd /home/jax/agent-os-poc/mvp
../.venv-mvp/bin/python check_mvp.py
```

已启用用户 linger，两个 API 用户服务随系统启动并在退出 SSH 后继续运行。数据库由系统 Docker 的重启策略管理。原离线 PoC 服务已停止并取消自动启动，文件保留。
Python 3.12.16 安装在 `agent-os-poc/.python`，MVP 依赖在 `.venv-mvp`，原系统 Python 和旧 `.venv` 保留。
已安装依赖记录在虚机 `requirements-mvp-installed.txt`。

PostgreSQL 已迁至宝塔安装的系统 Docker 26.1.4，使用 Compose 2.28.1 管理。项目为 `agentos-mvp`，容器为 `agentos-mvp-postgres`，在宝塔 Docker 的容器列表中按这个名称查找。Compose 文件为 `/home/jax/agent-os-poc/mvp/compose.postgres.yaml`。该部署接入系统 Docker；未修改宝塔面板的数据库或内部项目登记。

Docker 独立持久化数据卷为 `agentos-mvp-pgdata`，宿主位置 `/var/lib/docker/volumes/agentos-mvp-pgdata/_data`。2026-10-28按用户dbx直连需求，将端口同时发布到 `127.0.0.1:5532` 与 `192.168.1.166:5532`；应用凭证和服务端连接配置保持不变，dbx可用内网IP直连。容器重启策略为 `unless-stopped`，Docker 服务已启用开机启动；两个 API 通过 `wait_database.py` 在启动前等待数据库就绪，不再依赖原 Podman 用户服务。此次变更备份见项目记忆，旧归档Compose未包含内网映射。

原 rootless Podman 数据卷仍在 `/home/jax/.local/share/containers/storage/volumes/agentos-mvp-pgdata/_data`，与同名 Docker 数据卷是两个独立存储。原 Quadlet 已移为 `~/.config/containers/systemd/agentos-mvp-postgres.container.disabled`，防止重复占用5532端口。Podman 软件和原数据未删除。

镜像为 pgvector 官方 ARM64 镜像 `docker.io/pgvector/pgvector:0.8.7-pg18-trixie`，原 OCI 内容摘要为 `sha256:14d8a514128e8a98150fa391e522e05a8bf70e17bf1a69448fdb7a436c2187c6`。导入 Docker 后的镜像配置 ID 为 `sha256:644aabd4345d487db93e9a65f3b0e40af6b7f8b888db8c8d4c827a175902c604`，与 Podman 原镜像一致。启动时使用本地镜像，不再次拉取。

管理员凭证在虚机 `config/postgres.env`，应用凭证在 `config/postgres-app.json`，连接地址在 `config/mvp.json`；文件权限均为0600。应用账号不是超级用户，没有建库、建角色权限。框架使用已注册的数据库连接实例，序列化配置不包含数据库密码。

当前服务器数据库以 `compose.postgres.yaml` 为部署配置。历史初始化、迁移脚本和旧Podman配置已包含在完整归档中，不需要重复执行；恢复本地文件不等于获得数据库写入授权。

切换前的应用配置、源码、用户服务和 SQLite 快照保存在虚机 `backups/before-postgres/`。切回原 SQLite 时，应停止 API、恢复这份备份中的配置、源码和两个用户服务，再重载 systemd 并启动。切换后写入 PG 的新记录不会自动回写 SQLite；回退前应另存 PG 备份。

Podman → Docker 迁移前的备份在虚机 `backups/before-docker/`，包含完整 `agentos_mvp.dump`、数据指纹、连接配置和原用户服务。迁移时先停止两个 API，再导出数据库，在新 Docker 实例创建同名专用角色和空库，用 `pg_restore --single-transaction --exit-on-error` 恢复，校验全部16张应用表的数据指纹、归属、扩展和序列后才重启 API。

需要回退到 Podman 时，先停止 API 并备份 Docker 中的新数据，再停止 Docker PG；恢复备份中的 Quadlet 和两个旧 API 用户服务，重载用户 systemd 后启动原数据库及 API。原 Podman 数据仅保留到迁移时点，Docker 中的新记录不会自动同步回去。不要同时启动两边的 PG，也不要删除或混用两边的数据卷。

SSH 隧道断开时，在本机执行下列命令并按 SSH 提示认证。若某个本地端口已被现有隧道占用，保留已有隧道，只补另一个端口。

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:7777:127.0.0.1:7777 \
  -L 127.0.0.1:7778:127.0.0.1:7778 jax@192.168.1.166
```

回退到原离线验证服务：

```bash
systemctl --user disable --now agno-mvp-admin agno-mvp-employee
systemctl --user enable --now agno-poc
```

回退保留测试库。不要将含凭证的 `config/mvp.json` 复制进仓库。
源码修改后需部署到虚机 `mvp/` 并重启对应服务，修改本地文件不会自动更新虚机。

## 输出边界与下一步

服务端要求真实读取 Skill 后才导出结果。规则问答导出有限枚举和服务端固定文案；面试出题导出最后assistant生成的题单或业务答复、版本及运行引用。运行消息列表、工具原文与配置不导出。结果标记为 `byok_allowed`，允许进入员工模型上下文。

此版本不提供 `display_only` 通道，也不宣称任意问答都能保密：重复业务查询仍可能推断内部规则，需要按实际业务设计输出权限和查询限制。真实内部内容会发送给公司选择的模型中转；`store=False` 是协议请求，不能据此保证第三方中转不留日志。当前提供的中转地址使用 HTTP，正式环境应配置 HTTPS。

MVP 只对应一个令牌和固定测试身份 `mvp-jax`。PostgreSQL 已接入，但多员工 SSO、令牌撤销与权限映射、记录隔离、审批、持久化任务队列、产物管理、安全审计及数据库高可用和定期备份尚未实现。不要把同一个测试令牌分给全体员工，也不要直接开放管理端口。

规则问答和面试出题没有脚本执行工具，不要求额外沙箱。已接入 Agno 原生 DockerSandbox 的独立演示，见下文；真实市场调研采集尚未接入。数据库容器不作为任务沙箱使用。

`check_mvp.py` 会在已授权测试库中写入真实验证会话；`check_codex_client.py` 在本机临时 Codex 配置中测试一次 MCP 调用，使用本机已有登录，不修改日常工具审批设置。
# 原生 DockerSandbox 演示

AgentOS 的 Chat 列表新增“Docker 沙箱演示”（`docker-sandbox-demo`）。选择现有 Local AgentOS，先发送“生成一份测试报告”，再在同一会话发送“把标题改为沙箱验证成功，结论改成第二轮修改完成”。展开回复中的 `Worked for …` 可查看 `create_sandbox_report`、`revise_sandbox_report` 和 `inspect_sandbox` 的真实工具结果。最后可发送“释放沙箱”。

当前接法是普通模型 Agent 调用工具，工具通过本地 Unix socket 请求受控执行进程，后者使用 Agno `DockerSandbox.acreate/aexec/aget/adestroy`。模型本身仍在 AgentOS 进程运行，因此 `/agents` 中的 `sandboxed` 为 false；这与整套 CodexAgent/ClaudeAgent harness 在沙箱内运行的模式不同。

执行进程由系统服务 `agentos-sandbox-demo.service` 承载，仅该进程通过 `SupplementaryGroups=docker` 获得 Docker 权限，没有把 jax 加入 docker 组，也没有给 AgentOS 服务或沙箱挂载 Docker socket。服务仅监听 `/run/agentos-sandbox-demo/worker.sock`，不发布网络端口；接口只接受固定演示操作与有长度限制的文本，不接受任意命令、镜像、挂载路径或环境变量。

沙箱使用本地镜像 `agentos-sandbox-demo:20261028`，由 `Dockerfile.sandbox-demo` 离线构建，只包含本机已有基础镜像和独立 Python，不包含配置凭据、公司 Skill 源码或数据库。此镜像用于低层命令执行测试，并非完整的 Agno coding-harness runtime 镜像。

限制：非 root、只读根目录、无网络、1 CPU、256 MiB、64 PID、32 MiB 工作区，最多同时两个演示容器。每30秒检查过期会话，闲置15分钟后销毁容器；导出的报告和操作记录保留在 `data/sandbox-demo/<会话散列>/`。容器内工作区没有做检查点，容器销毁后不恢复原工作区；重新生成会创建新一代容器。报告版本保留不代表容器工作区持久化。

报告预览经管理 API 的 `/sandbox-demo/<会话散列>/report-vN.html` 路径提供，只能通过现有操作者 SSH 转发访问。该路径复用当前管理端的单人内网访问范围，未添加多员工认证。页面为简单演示HTML，不调用市场数据源，也未接入正式市场报告模板。

服务器验证命令：

```bash
/home/jax/agent-os-poc/.venv-mvp/bin/python /home/jax/agent-os-poc/mvp/check_sandbox_demo.py
systemctl status agentos-sandbox-demo.service
```

## 历史面试出题 Skill 发布演练（2026-10-28）

以下为旧版发布时点记录；当前版本与入口以上方2026-11-05章节为准，管理端已清理为空。

已将本机 `java-interview-assessment` 原始7个文件发布为 `20261028.1`，服务器位置为 `mvp/private-skills/releases/20261028.1/java-interview-assessment/`。内容与本机原件一致，发布后文件只读。该包只有说明、参考资料与模板，没有脚本，因此本次无需构建镜像、安装依赖或新增凭据。

`config/interview-release.json` 记录版本、文件hash、来源总hash、绑定Agent、测试范围、发布状态和验收运行编号。此为本次手工发布记录，不是已实现的通用发布后台。原版发布记录及管理、员工入口源码备份在 `backups/before-interview-release/`。

管理端 Chat 选择“Java 面试出题”（`java-interview-agent`），可以输入简历文本与岗位要求。该Agent只绑定本次面试Skill；默认读取原说明、出题方法、评分规范和固定模板，无任意文件、脚本执行或Obsidian工具。生成题单与评分参考，不填候选人成绩、不进行录用决策。

员工 MCP 新增 `generate_interview_questions(request, session_id=None)`。首次调用可省略会话编号，空字符串也视为新任务；修改时使用返回的 `interview-...` 编号。继续请求会核对当前固定测试身份与Agent归属。发布状态为 `testing` 时拒绝执行，`published` 时供同一Jax测试令牌使用；尚无多员工身份映射。

MCP只返回业务答复、Skill版本和运行引用，不返回私有工具调用、说明或参考文件原文；当前为可进入员工模型上下文的 `byok_allowed` 演示结果。出口检查不构成通用提示注入或方法推断防护保证。

本机 Codex 的原 MCP 配置已添加该业务工具，原审批设置保持不变。当前对话若未发现新工具，需要重连MCP或新开对话。可输入：

> 调用公司MCP的generate_interview_questions：先出一份Java后端通用面试题。Java17、Spring6.2，只要一道基础题，包含参考答案、五个评分点和空白记录表。

真实Codex验收脚本为 `check_interview_codex.py`。测试使用虚构或通用资料；当前接口只收文本，未提供PDF解析、Obsidian写入或候选人评估能力。

