---
name: boss-zhipin-scraper
description: "Scrape BOSS直聘 (job listing site) via Chrome CDP. Searches jobs by keyword/city/filters, fetches JD details, outputs structured JSON/CSV with plaintext salary, and can summarize scraped results into a job-market prompt. Use when user wants to search/analyze jobs on BOSS直聘 or zhipin.com."
version: 2.0.0
author: eatmoreduck
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [scraper, jobs, career, cdp, chrome, zhipin, boss直聘]
---

# BOSS直聘职位抓取工具 v2.0

通过 Chrome CDP 协议抓取 BOSS直聘 (zhipin.com) 职位数据，输出结构化 JSON/CSV（含明文薪资），并可对已抓取结果生成聚合摘要和求职材料优化提示词。

## 前置条件

- Chrome 浏览器已安装
- Python 3.10+
- 用户已登录 zhipin.com（或愿意手动登录）

## 脚本位置

本 skill 的脚本在 skill 目录下：

- `scripts/boss_cdp_raw.py`：抓取主脚本
- `scripts/job_summary.py`：抓取后摘要和提示词脚本

**运行任何命令前，必须先确定脚本的绝对路径。**

用以下方式找到脚本（macOS 自带的 `readlink` 不支持 `-f`，用 Python 解析路径更通用）：

```bash
# 方法 1：已知 skill 安装目录（推荐，macOS/Linux 通用）
SKILL_DIR="$(python3 -c "import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))" "$0")"
SCRIPT_PATH="$SKILL_DIR/scripts/boss_cdp_raw.py"
SUMMARY_PATH="$SKILL_DIR/scripts/job_summary.py"

# 方法 2：搜索 hermes skills 目录
SCRIPT_PATH=$(find ~/.hermes/skills -name "boss_cdp_raw.py" -type f 2>/dev/null | head -1)
SUMMARY_PATH=$(find ~/.hermes/skills -name "job_summary.py" -type f 2>/dev/null | head -1)
```

如果找不到脚本，说明 skill 未正确安装，需要重新安装。

## 依赖安装（首次使用必须执行）

脚本依赖 `websocket-client` 和 `requests`。在用户项目的 venv 中安装：

```bash
uv add websocket-client requests
# 或
pip install websocket-client requests
```

## 自动化流程

当用户要求搜索/抓取 BOSS直聘 职位时，**严格按以下顺序执行**：

### 第 1 步：检查环境

```bash
python3 "$SCRIPT_PATH" --check --cdp-port 9222
```

检查三项：Python 依赖 → CDP 连通性 → 登录态。

- **全部通过** → 跳到第 3 步
- **CDP 不通** → 继续第 2 步
- **依赖缺失** → 先装依赖（见上方依赖安装），再重新 --check
- **未登录** → 告诉用户打开 Chrome 登录 zhipin.com，然后重新 --check

### 第 2 步：启动 Chrome CDP（仅在 --check CDP 不通时）

```bash
python3 "$SCRIPT_PATH" --setup-chrome --cdp-port 9222
```

这会自动完成：
1. 创建或复用持久隔离 Chrome profile
   - `~/.boss-zhipin-scraper/chrome-profile`
2. 只关闭使用该隔离 profile 的旧 BOSS CDP Chrome，不关闭用户主 Chrome
3. 以 CDP 模式启动 Chrome（`--remote-debugging-port=9222`）
4. 等待 CDP 端口就绪（最多 30 秒）
5. 打开 BOSS 登录页并等待登录完成，直到搜索接口返回明文 `salaryDesc`

默认不复制主 Chrome 的 Cookie、密码、历史记录或扩展；首次启动和后续重复启动都只是创建或复用该专用 profile。首次使用时告诉用户：请在弹出的 BOSS 专用 Chrome 浏览器中访问 zhipin.com 并登录。脚本会等待登录完成并确认接口能返回明文薪资。该专用 profile 是持久目录，机器重启后登录态仍保留，重复运行 `--setup-chrome` 不会清空它。

仅当用户明确要求从主 Chrome 手动导入 BOSS 登录态时，可使用：

```bash
python3 "$SCRIPT_PATH" --setup-chrome --copy-login-state --cdp-port 9222
```

`--copy-login-state` 每次运行都会覆盖隔离 profile 内对应的 Cookie 相关文件；日常启动不要加这个参数。它只复制 `Local State` 和 `Default/Cookies*`、`Default/Network/Cookies*` 这类 Cookie 数据库相关文件，不复制密码库或完整 profile。不要默认使用该参数，也不要告诉用户首次启动会自动导入主 Chrome 登录态。

等用户确认后，重新运行 `--check` 验证。

### 第 3 步：运行抓取

```bash
# 基础搜索
python3 "$SCRIPT_PATH" --keyword "关键词" --city 城市 --pages 3 --output ~/.boss-zhipin-scraper/job-result/jobs.json

# 带 CSV 输出
python3 "$SCRIPT_PATH" --keyword "关键词" --city 城市 --pages 3 --format csv --output ~/.boss-zhipin-scraper/job-result/jobs.json

# 带详情 + 分析报告
python3 "$SCRIPT_PATH" --keyword "关键词" --city 城市 --pages 3 --detail --max-details 8 --analysis --format csv --output ~/.boss-zhipin-scraper/job-result/jobs.json

# 抓取后摘要 + 求职材料优化提示词（默认读取最新抓取结果）
python3 "$SUMMARY_PATH" --top 15

# 真实浏览器/API smoke test（不写结果文件）
python3 "$SCRIPT_PATH" --smoke-test --cdp-port 9222

# 合并多次抓取（去重）
python3 "$SCRIPT_PATH" --keyword "关键词" --city 北京 --pages 3 --merge ~/.boss-zhipin-scraper/job-result/jobs.json --output ~/.boss-zhipin-scraper/job-result/jobs_merged.json
```

默认输出到 `~/.boss-zhipin-scraper/job-result/` 目录，`--format csv` 会给列表和详情都额外生成 `.csv` 文件。`--smoke-test` 只验证真实 Chrome/CDP 能否拿到 API 明文薪资，不写结果文件。

摘要脚本只读取 `boss_jobs_*.json` 和 `boss_details_*.json`，不读取本地简历文件，不引入 PDF 依赖，也不给个人与岗位做分数判断。需要指定文件时使用：

```bash
python3 "$SUMMARY_PATH" \
  --input ~/.boss-zhipin-scraper/job-result/boss_jobs_20260625_1200.json \
  --details ~/.boss-zhipin-scraper/job-result/boss_details_20260625_1200.json \
  --top 15
```

## 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--keyword` | AI Agent | 搜索关键词 |
| `--city` | 上海 | 城市名（中文）或代码；没传时默认上海 |
| `--pages` | 3 | 抓取页数（上限 10，每页 30 条） |
| `--output` | ~/.boss-zhipin-scraper/job-result/... | 列表输出路径 |
| `--detail-output` | ~/.boss-zhipin-scraper/job-result/... | 详情输出路径 |
| `--format` | json | 输出格式: json / csv；csv 同时导出列表和详情 CSV |
| `--detail` | 开启（默认） | 抓取详情页 JD |
| `--no-detail` | - | 不抓取详情页（关闭默认行为） |
| `--max-details` | 全部 | 详情页数量上限 |
| `--analysis` | 关闭 | 输出分析报告 |
| `--allow-dom-fallback` | 关闭 | API 无数据时允许降级 DOM 提取；默认关闭，薪资可能不可信 |
| `--merge FILE` | - | 合并已有 JSON（按 job_id 去重） |
| `--cdp-port` | 9222 | CDP 端口 |
| `--setup-chrome` | 关闭 | 一键启动 Chrome CDP（持久隔离 profile） |
| `--copy-login-state` | 关闭 | 手动导入主 Chrome 的 Local State + Cookie 相关文件到隔离 profile；默认、首次启动、重复启动都不复制 |
| `--reset-chrome-profile` | 关闭 | 重建 BOSS 专用 profile，会清除此专用浏览器登录态 |
| `--no-wait-login` | 关闭 | `--setup-chrome` 启动后不等待 BOSS 登录完成 |
| `--login-timeout` | 300 | `--setup-chrome` 等待登录完成的秒数 |
| `--check` | 关闭 | 环境检查 |
| `--smoke-test` | 关闭 | 真实 Chrome/CDP 搜索 API smoke test，不写结果文件 |
| `--version` | - | 查看版本号 |

### 筛选参数

| 参数 | 值 |
|------|-----|
| `--scale` | 301=0-20人 302=20-99 303=100-499 304=500-999 305=1000-9999 306=10000+ |
| `--salary` | 402=3K以下 403=3-5K 404=5-10K 405=10-20K 406=20-50K 407=50K+ |
| `--experience` | 108=在校生 102=应届生 101=经验不限 103=1年内 104=1-3年 105=3-5年 106=5-10年 107=10年+ |
| `--degree` | 209=初中及以下 208=中专/中技 206=高中 202=大专 203=本科 204=硕士 205=博士 |

### 城市代码

全国 100010000 | 北京 101010100 | 上海 101020100 | 广州 101280100 | 深圳 101280600 | 杭州 101210100 | 成都 101270100 | 武汉 101200100 | 南京 101190100 | 厦门 101230200

## 输出格式

### JSON

```json
{
  "keyword": "AI Agent",
  "city": "上海",
  "total": 60,
  "jobs": [
    {
      "job_id": "c4420e8bce3a6e25",
      "title": "AI Agent工程师",
      "salary": "30-60K·15薪",
      "location": "上海·闵行区·虹桥",
      "tags": "5-10年 | 本科",
      "boss_name": "SHEIN",
      "boss_title": "招聘者",
      "company_scale": "10000人以上",
      "company_stage": "D轮及以上",
      "company_industry": "电子商务",
      "skills": "Java | Spring | AI",
      "job_link": "https://www.zhipin.com/job_detail/xxx.html",
      "company_link": "https://www.zhipin.com/gongsi/xxx.html",
      "welfare": "节日福利 | 零食下午茶 | 定期体检"
    }
  ]
}
```

### CSV

`--format csv` 时自动在同目录生成 `.csv` 文件：列表 CSV 跟随 `--output`，详情 CSV 跟随 `--detail-output` 或默认详情 JSON 路径。CSV 使用 UTF-8 BOM 编码，Excel 直接打开无乱码。

## 工作原理

1. 通过 Chrome DevTools Protocol (CDP) 连接到已打开的 Chrome 浏览器
2. 在 BOSS直聘页面内注入 JS，用同步 XHR 调用 `/wapi/zpgeek/search/joblist.json` API
3. API 返回明文 `salaryDesc`（如 `30-60K·15薪`），绕过前端字体反爬
4. 列表 API 保留 `securityId` / `lid` 等上下文，进入详情页时带上这些参数
5. 默认禁用 DOM fallback，避免把字体反爬后的薪资写入结果；只有显式 `--allow-dom-fallback` 才降级
6. 每页 30 条，每页抓完立即写入文件，异常退出不丢数据
7. 按 `job_id`（job_link 的 MD5 哈希前 16 位）去重

## 数据安全策略

`--setup-chrome` 默认使用持久隔离 profile，不软链接、不读取、不复制主 Chrome profile。首次启动和后续重复启动都只会创建或复用 `~/.boss-zhipin-scraper/chrome-profile`，不会清空其中的 BOSS 登录态。setup 会等待登录完成，并用多组关键词/城市 probe，要求搜索接口返回明文薪资；如果一直拿不到 `salaryDesc`，不要继续抓取并把 DOM 薪资当成可信数据。这样 CDP 只暴露 BOSS 专用浏览器里的数据，不影响用户主 Chrome、Gmail、GitHub 等账号。

`--input ... --analysis --no-detail` 会优先加载 `--detail-output`，其次加载与输入列表同目录、同时间戳的 `boss_details_*.json`，最后查找 `~/.boss-zhipin-scraper/job-result` 下最新详情文件。

需要清空 BOSS 专用浏览器登录态时使用：

```bash
python3 "$SCRIPT_PATH" --setup-chrome --reset-chrome-profile --cdp-port 9222
```

## 常见问题

1. **--check CDP 不通** → 运行 `--setup-chrome`
2. **--check 未登录** → 在专用 Chrome 中访问 zhipin.com 登录，或重新运行 `--setup-chrome`
3. **薪资空白** → 通常是未登录、登录态失效或接口未返回 `salaryDesc`；先重新登录，不要优先做字体解密或 DOM fallback
4. **抓取中断** → 重新运行即可，增量写入 + 自动去重
5. **端口占用** → `--cdp-port 9223` 换端口
6. **Chrome 启动失败** → `--cdp-port 9223` 换端口，或用 `--reset-chrome-profile` 重建专用 profile

## 注意事项

- 仅用于个人求职研究
- 单次最多 10 页（300 条），防封号
- 翻页间隔 12-22 秒随机延迟，3 页约 1 分钟
- 详情页每条 10-25 秒，10 条约 3-5 分钟
- BOSS直聘可能更新 API 路径，失效时需更新脚本中 `API_JOB_LIST_PATH` 常量

## 安装本 Skill

本 Skill 需手动安装到 Hermes skills 目录（`hermes skills install` 因网络问题可能失败）：

```bash
# 推荐：curl 一键安装
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/SKILL.md \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/SKILL.md && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/boss_cdp_raw.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/boss_cdp_raw.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/job_summary.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/job_summary.py
```

或克隆后手动复制：

```bash
git clone https://github.com/eatmoreduck/boss-zhipin-scraper.git
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts
cp boss-zhipin-scraper/SKILL.md ~/.hermes/skills/data-science/boss-zhipin-scraper/
cp boss-zhipin-scraper/scripts/boss_cdp_raw.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/
cp boss-zhipin-scraper/scripts/job_summary.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/
```
