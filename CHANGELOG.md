# Changelog

## 未发布

### 变更
- 新增 Issue 标签约定（#58）：`CONTRIBUTING.md` 增加标签语义表与打标原则（`wontfix`/`invalid` 关闭须留理由），`AGENTS.md` 补 issue 分诊打标指引；开放 issue 已完成首轮打标
- 文档同步被动捕获架构（#56）：`AGENTS.md` 重写架构关键点（列表=Network 被动捕获、焦点仿真进 CDP 不变量、BOSS 页面行为事实），新增两条硬规则（动抓取链路必须真机 e2e；合规红线：只被动捕获、禁止指纹伪造/验证码绕过/代理轮换），补合并惯例与 spike 脚本约定；README 双语登录探测段落同步为被动捕获表述
- 列表抓取与登录探测全面改为**被动捕获**（#53/#30）：不再向页面注入同步 XHR（该请求模式会被 BOSS 风控识别为 code 37），改为导航真实搜索页后通过 CDP `Network` 域旁听页面自身发出的 `joblist.json` 响应；翻页改为滚动触发页面自身的无限滚动加载（每页 15 条，`hasMore=false` 时提前结束）。字段映射逻辑从注入 JS 模板迁至 Python（`map_api_job`）
- 登录/风控判定并入首次真实搜索响应（`LoginGateError`）：正式抓取不再预先发送固定 `Java/上海` 登录探测，消除一次无关请求；`--check`、`--setup-chrome` 的探测同样改为被动捕获，消息与退出语义不变
- 后台标签页开启 `Emulation.setFocusEmulationEnabled` 焦点仿真：页面自身的无限滚动加载在真实后台（不可见、无焦点）状态下不触发，仿真后 `document.hidden=false / visibilityState=visible / hasFocus=true`，且不激活窗口、不抢前台焦点
- 删除死代码：`FETCH_API_JS_TEMPLATE`、`build_login_probe_url`、`parse_api_jobs_eval_value`、`should_use_dom_fallback`；`CDPSession` 新增事件缓冲与 `drain_events`；测试从 92 增至 96 个

### 新增
- 详情/列表结果新增独立字段 `boss_active_status`（如「今日活跃」「在线」）：列表兼容 `activeTimeDesc` 与 `bossOnline`（仅在线时映射为「在线」）；详情页从招聘者卡片解析更细粒度状态并优先保留；JD 正文仍剔除该行，不混入描述
- 新增 `--stop-chrome` 命令：抓取/分析完成后关闭 BOSS 专用 CDP Chrome（按 user-data-dir 精准匹配隔离 profile，不碰主 Chrome）；抓取命令新增 `--close-chrome` 选项，正常结束后自动收尾（默认关闭，异常退出不触发以保留登录态）。复用已有 `stop_cdp_chrome` 的安全匹配逻辑，补齐进程关闭/收尾链路的单元测试。（#26）
- 城市码表外置为 `data/city_codes.json`（全量 300+ 城市，覆盖一二三四五线），新增 `--list-cities [关键词]` 命令查看支持的城市；`resolve_city` 查询链改为「本地静态码表 → 运行时拉 BOSS 接口 → 9 位裸码兜底」。城市码表打进 wheel，`pip install` 用户也可用。（#24）

### 修复
- Windows 兼容：`main()` 入口将 stdout/stderr 重配为 UTF-8，修复 Windows GBK 控制台遇到 emoji（✅❌⚠️ 等）输出直接 `UnicodeEncodeError` 崩溃的问题（实测此前 73 个单测中 8 个因此失败）
- JSON 落盘改为原子写入（临时文件 + `os.replace`）：进程中断不再留下半截 JSON 覆盖旧数据；`flush_jobs`、详情页写入与 `--merge` 详情落盘统一走 `_atomic_write_json`
- `--check` 的 CDP 连通检查不再把任意 CDP 服务误报为「Chrome」，改为输出实际服务标识
- 清理死代码与重复实现：删除无调用方的 `append_json`；`flush_jobs`/`merge_jobs`/`merge_details_from_lists` 的读-去重-写收敛到 `merge_unique`；`parse_jobs_eval_value` 与 `parse_api_jobs_eval_value` 合并（smoke test 改用后者，行为不变）
- 测试平台适配：Chrome 进程查询的 mock 输出改为按平台生成（Windows 分支解析 PowerShell JSON、POSIX 分支解析 ps 文本），修复 Windows 上 3 个既有测试失败；`test_help_does_not_require_cdp_runtime_dependencies` 显式指定 UTF-8 解码；新增 `merge_unique` / `_atomic_write_json` / `flush_jobs` 单元测试（全量 92 个测试通过）
- 城市解析先执行本地及在线码表的正反向映射，再接受未收录的 9 位裸城市码；未知城市名现在会在抓取前明确报错退出。在线城市接口同时校验业务 `code`，不再把 `code: 35` 等风控响应静默当作空码表
- 登录探测识别 BOSS 风控码 `code: 37`「您的环境存在异常」为限制状态（RESTRICTED），并对未知风控码按 message 关键字（环境存在异常、访问频繁、安全校验等）兜底识别；避免已登录但被风控/限流的用户被误判为「登录探测响应异常」而无法继续。（#33）
- 登录探测改为区分可用、未登录、限制、空结果和响应异常；每轮仅请求一次并采用有上限的退避等待，`code: 31` 等明确限制会立即停止。探测请求现已纳入全局请求预算，CLI 不再把风控或异常统一提示为未登录。（#31）
- 修复 Chrome 151 真实环境中后台 Target 无法取得 BOSS 搜索响应的问题（#67）：登录检查、列表抓取和 smoke test 改用前台临时标签页；详情抓取继续使用后台 Target、visibility override 和焦点仿真
- 详情页 JD 改为只提取“职位描述”区，并在登录墙、导航页或过短正文出现时拒绝写入，不再把整页 `body`、招聘者信息、公司介绍和推荐职位当作 JD
- 同步 BOSS 当前 `city.json` / `condition.json` 映射，修正城市码以及薪资、经验、学历筛选枚举漂移，并在内置城市表未命中时自动加载 BOSS `cityGroup.json` 支持更多城市中文名
- `scrape_details` 最终保存改用 `os.path.dirname(path) or "."`，`--detail-output` 传不带目录的裸文件名时不再抛 `FileNotFoundError`（与循环内及其它写文件处保持一致）
- 修正城市码：天津 `101030100`、沈阳 `101070100`（原均误用 `101060100`）
- `require_runtime_dependencies` 缺失依赖时同时提示 uv 和 pip 安装方式
- `--merge` 现在会合并旧详情并落盘到 `--detail-output`（之前只合并列表，详情丢失）
- API URL filter 改用 `urlencode`（原字符串拼接，filter 值含特殊字符会出错）

### 变更
- 平台支持声明更新：Windows 已通过单元测试与基础 CLI 验证（GBK 控制台崩溃等已修复），README 中英双语同步调整（此前 v2.0.0 撤回的"未经实测"声明在本修复后更新）
- 平台支持声明改为 macOS + Linux（Windows 代码分支保留但未经实测，不再声称支持，避免过度承诺）
- `pyproject.toml` 删除空的 `[csv]` extra（csv 是标准库）
- SKILL.md 脚本路径解析改用 Python `os.path.realpath`（macOS 自带 `readlink` 无 `-f`）

### 新增
- `scripts/job_summary.py` 抓取后摘要脚本：读取已有 JSON，输出岗位聚合摘要和求职材料优化提示词
- `boss-summary` 命令行入口，便于打包安装后直接运行摘要脚本
- 抓取后摘要测试：覆盖 JSON 加载、聚合维度、提示词输出和项目边界
- 版本号一致性测试：校验脚本、pyproject.toml、SKILL.md、README.md 四处版本同步
- CONTRIBUTING.md 贡献指南

## v2.0.0 (2026-06)

### 新功能
- `--check` 环境检查（CDP 连通性、依赖、登录态）
- `--setup-chrome` 一键启动 Chrome CDP（持久隔离 profile）
- `--copy-login-state` 手动导入主 Chrome 的 Local State + Cookie 相关文件到隔离 profile
- `--reset-chrome-profile` 重建 BOSS 专用 Chrome profile
- `--setup-chrome` 默认等待 BOSS 登录完成，并确认接口返回明文薪资
- `--no-wait-login` / `--login-timeout` 控制 setup 登录等待
- 默认抓取结果保存到 `~/.boss-zhipin-scraper/job-result`
- 未传 `--city` 时默认搜索上海
- `--format csv` 同时导出列表 CSV 和详情 CSV
- `--merge` 合并多次抓取结果（去重）
- `--cdp-port` 自定义 CDP 端口（默认 9222）
- `--smoke-test` 用真实 Chrome/CDP 跑一次搜索 API smoke test，不写结果文件
- `--allow-dom-fallback` 显式允许 API 失败时降级 DOM 提取
- `--version` 查看版本号
- 登录态检测：未登录时给出明确提示
- 分析报告技术词动态提取（不再硬编码）
- 进度显示：`[2/3 页, 45/90 条]`

### 改进
- CDP WebSocket 消息过滤 + 超时重试（不再无限卡死）
- 详情页写入去重（中断重跑不重复）
- 请求频率保护（最多 10 页，全局 500 次上限）
- 清除所有 bare except，改为具体异常类型
- API 路径提取为常量，方便维护
- DOM fallback 标记为 deprecated
- DOM fallback 默认关闭，避免把字体反爬后的薪资写进结果
- API 错误行不再被当成职位数据处理
- 详情输出保留 `job_id`、`job_link` 和 `salary_source`
- 详情页访问会带上列表 API 返回的 `securityId` / `lid` 上下文
- `--input ... --analysis --no-detail` 会从 `--detail-output`、同目录同时间戳详情文件、默认结果目录最新详情文件中加载详情
- 登录态检测改为多关键词、多城市 probe，但仍要求接口返回明文薪资
- Linux / Windows 平台支持（Chrome 路径 + 隔离 profile）
- pyproject.toml 版本锁定依赖

### 安全
- 默认不软链接、不复制主 Chrome profile；首次启动也不自动导入主 Chrome 登录态，避免影响 Gmail/GitHub 等主浏览器登录态
- API URL 可配置（`API_JOB_LIST_PATH` 常量）

## v1.0.0 (2026-06)

### 初始版本
- Chrome CDP 抓取 BOSS直聘职位列表
- API 明文薪资（绕过字体反爬）
- 详情页 JD 抓取 + 技能标签提取
- 增量写入（异常退出不丢数据）
- 分析报告（薪资分布、经验要求、简历建议）
- 多维筛选（规模、融资、薪资、经验、学历、行业）
