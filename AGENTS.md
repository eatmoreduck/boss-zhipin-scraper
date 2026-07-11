# AGENTS.md

指引给未来的 ZCode agent。先读这份，再动代码。

## 这是什么

`boss-zhipin-scraper` —— 通过 Chrome CDP（远程调试端口）连接**用户本人已登录的 Chrome**，抓取 BOSS直聘的公开职位数据（列表 + 详情），并可生成求职分析摘要。仅用于个人求职分析，非大规模爬虫（见 `CONTRIBUTING.md` 的合规一节）。

## 目录结构

```
scripts/boss_cdp_raw.py   # 核心：抓取 + CLI 主入口（~1900 行，单文件）
scripts/job_summary.py    # 抓取结果 → Markdown 求职分析摘要
tests/test_chrome_setup.py    # unittest，全 mock，不依赖真实 Chrome/网络
tests/test_job_summary.py     # 摘要测试
pyproject.toml            # hatchling 打包；入口 boss-scraper / boss-summary
requirements.txt          # 仅 requests + websocket-client
SKILL.md / README(.en).md / CHANGELOG.md / CONTRIBUTING.md
```

**重要边界：核心逻辑都放 `scripts/boss_cdp_raw.py`，不要随手新建文件**（见 `CONTRIBUTING.md`「单文件原则」）。`docs/` 被 `.gitignore` 忽略，是本地产物，不要提交。

## 环境与命令

- Python **>=3.10**，依赖只有 `requests` + `websocket-client`。用项目里的 `.venv`（`source .venv/bin/activate`），别用 pyenv 全局解释器（会缺依赖报错）。
- 包管理用 `uv`（仓库有 `uv.lock`），也可 `pip install -r requirements.txt`。
- 跑测试：`python3 -m unittest tests.test_chrome_setup`（无需 Chrome / 联网，全 mock）。改了 `job_summary` 再加跑 `tests.test_job_summary`。
- 语法自检：`python3 -m py_compile scripts/boss_cdp_raw.py`。
- 实跑抓取需要先启动带调试端口的 Chrome：`python3 scripts/boss_cdp_raw.py --setup-chrome`（开 `127.0.0.1:9222`，默认端口见 `DEFAULT_CDP_PORT`），登录后在**另一个终端**跑抓取命令。Chrome 关了端口就没了。

## 改代码时的硬规则

1. **版本号四处一致**：`scripts/boss_cdp_raw.py` 的 `__version__`（第 22 行附近）、`pyproject.toml`、`SKILL.md`、`README.md` 必须同步，否则 `VersionConsistencyTests` 会挂。改版本号时四处一起改。
2. **异常处理**：禁止 bare `except:`，必须捕获具体类型（`requests.ConnectionError`、`json.JSONDecodeError` 等），和现有代码保持一致。
3. **改了用户可见行为 → 更新 `README.md`；有意义变更 → `CHANGELOG.md` 顶部加一条。**
4. **README 双语同步**：`README.md`（中文）和 `README.en.md`（英文）必须保持一致，改了其中一个就要同步另一个。
5. **commit message 用 Conventional Commits**（`feat:` / `fix:` / `docs:` / `optimize:` / `refactor:` 等，见 `CONTRIBUTING.md`）。

## 架构关键点（容易踩坑）

- `scripts/boss_cdp_raw.py` 是一个**长单文件**，包含：`CDPSession` 类（WebSocket 连 CDP）、城市码表、各种 `EXTRACT_*_JS` 注入脚本、`scrape_jobs`（列表走 `/wapi/...` API）、`scrape_details`（详情走新开 tab 渲染）、`main`（argparse）。
- **列表页 vs 详情页路径完全不同**：列表页通过页面内 `fetch` 调 BOSS wapi（带 token，不经页面渲染）；详情页通过 `Target.createTarget` 新开 tab → `Page.navigate` → 注入 JS 提取。改其中一条路径时，另一条不受影响。
- **CDP `background:true` 的坑（issue #18）**：后台 tab 的 `document.hidden=true` 会触发 BOSS visibility 反爬，导致详情抓空。当前在 `scrape_details` 导航前用 `Page.addScriptToEvaluateOnNewDocument` 注入脚本覆盖可见性属性为 visible。动详情页逻辑时别破坏这段。
- 同一个 Chrome 实例的默认 browser context 下，新开 target **本就共享 cookies**，不要被「新 tab 丢 cookie」的直觉误导。
- `require_runtime_dependencies("requests", "websocket")` 在多个入口前置检查依赖，缺了会提示安装。

## 提交流程

默认分支 `master`，fork/分支工作流：从 `master` 拉新分支（`fix/...`、`feat/...`）→ 改代码补测试 → push → PR。一个 PR 只做一件事。
