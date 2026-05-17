# Aether Batch Sign-up

使用 Gmail 别名在 [Aether (to-aether.com)](https://to-aether.com) 批量注册账号并创建 API Key 的自动化工具。

## 工作原理

1. 使用 Gmail 的 `+` 别名（`yourname+1@gmail.com`, `yourname+2@gmail.com`...）注册 Aether
2. 验证码邮件发送到主邮箱，通过 POP3 自动读取
3. 通过 **CapSolver** 自动解决 Cloudflare Turnstile 验证
4. 注册成功后登录并遍历所有渠道分组创建 API Key
5. 汇总结果输出到 `aether_accounts.json`

## 前置准备

1. **Gmail 开启 POP3**: Gmail 设置 → 转发和 POP/IMAP → 启用 POP 下载
2. **Gmail 应用密码**: Google 账号 → 安全性 → 应用专用密码（需要开启两步验证）
3. **CapSolver API Key** (可选): 注册 https://www.capsolver.com/ 获取 API Key
   - 用于自动解决 Cloudflare Turnstile（约 $0.001/次）
   - 如果不用，可以手动提供 Turnstile Token（有效期约 5 分钟）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env` 并填写：

```env
# 必要配置
GMAIL_EMAIL=dijiaozhibei@gmail.com
GMAIL_APP_PASSWORD=pfca nrvg bqqb hthu
ACCOUNT_PASSWORD=AetherTest123!
ACCOUNT_EMAIL_BASE=dijiaozhibei

# 批次范围
BATCH_START=2
BATCH_END=5

# 以下二选一：

# 方式 A: CapSolver 自动解 Turnstile
CAPSOLVER_API_KEY=CAP-xxxxx

# 方式 B: 手动 Token（通过 src/get_turnstile.py 获取）
# TURNSTILE_TOKEN=0x...

# 指定渠道分组（留空=所有分组）
# TARGET_GROUPS=Claude Chat,OpenAI Codex
```

### 3. 运行

```bash
# API 模式（推荐，需 CapSolver）
python -m src.main

# 或先手动获取 Turnstile Token
python src/get_turnstile.py   # 会打开浏览器
# 复制输出的 token 到 .env 的 TURNSTILE_TOKEN
python -m src.main
```

### 4. 查看结果

```bash
cat aether_accounts.json
```

## GitHub Actions 自动运行

### 配置 Secrets

在 GitHub 仓库设置中添加以下 Secrets：

| Secret | 说明 |
|--------|------|
| `GMAIL_EMAIL` | Gmail 完整邮箱地址 |
| `GMAIL_APP_PASSWORD` | Gmail 应用专用密码 |
| `ACCOUNT_PASSWORD` | 注册账号的密码 |
| `ACCOUNT_EMAIL_BASE` | 邮箱前缀，例如 `dijiaozhibei` |
| `CAPSOLVER_API_KEY` | (可选) CapSolver API Key |
| `TURNSTILE_TOKEN` | (可选) 手动 Turnstile Token |
| `TARGET_GROUPS` | (可选) 目标分组，逗号分隔 |

### 手动触发

GitHub → Actions → Aether Batch Registration → Run workflow

### 自动触发

默认每天 UTC 2:00 自动运行（可修改 `batch.yml` 中的 cron 表达式）。

## 文件结构

```
.
├── .github/workflows/batch.yml   # GitHub Actions 工作流
├── src/
│   ├── __init__.py
│   ├── config.py                 # 配置管理
│   ├── aether_api.py             # Aether API 客户端
│   ├── gmail_pop3.py             # Gmail POP3 邮件读取
│   ├── main.py                   # 主入口（批量注册）
│   ├── get_turnstile.py          # 手动获取 Turnstile Token
│   └── playwright_bot.py         # Playwright 浏览器自动化
├── .env.example                  # 配置示例
├── requirements.txt              # Python 依赖
└── aether_accounts.json          # 运行结果（自动生成）
```
