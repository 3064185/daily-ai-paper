# AI 前沿与论文日报 Daily Digest

每天北京时间 09:00 自动生成 AI 前沿新闻 + 计算机科学论文日报，并通过邮件发送。

## 功能

- AIHOT 中文 AI 新闻 RSS 抓取
- 6 个论文来源独立检索：arXiv、Semantic Scholar、OpenAlex、Crossref、DBLP、Papers with Code
- OpenAI 结构化分析（自动回退到规则评分）
- 开放获取 PDF 全文自动读取与分析
- Markdown / HTML / Excel / SQLite 多格式输出
- SMTP SSL 邮件发送（3 次重试）
- 单个数据源失败不影响整体生成

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入配置

# 无邮件运行测试
python3 daily_pipeline.py --no-email

# 检查环境
python3 check_environment.py

# 发送测试邮件
python3 send_daily_report_email.py --test
```

## GitHub Actions 定时运行

项目默认通过 GitHub Actions 每天 UTC 01:17（北京 09:17）自动运行。

需要在 repo Settings → Secrets and variables → Actions 中配置：

| Secret | 说明 |
|--------|------|
| `EMAIL_HOST` | SMTP 服务器 (smtp.qq.com) |
| `EMAIL_PORT` | SMTP 端口 (465) |
| `EMAIL_USER` | 发件邮箱地址 |
| `EMAIL_PASSWORD` | SMTP 授权码 |
| `EMAIL_TO` | 收件邮箱 |
| `OPENAI_API_KEY` | (可选) OpenAI API key |

## 本机定时任务 (macOS launchd)

```bash
cp com.daily-ai-paper.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.daily-ai-paper.plist
```

## 输出产物

`outputs/` 目录下：
- `daily_combined_report_YYYYMMDD.md` / `.html` — 合并日报
- `daily_aihot_YYYYMMDD.xlsx` — AI 新闻 Excel
- `daily_cs_papers_YYYYMMDD.xlsx` — 论文 Excel
- 根目录 `aihot_database.sqlite` / `papers_database.sqlite` — 历史记录
- `outputs/daily_sent_YYYYMMDD.ok` — 邮件发送成功标记
