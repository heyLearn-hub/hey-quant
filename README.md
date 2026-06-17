# 美股科技/半导体/AI 低频量化提醒系统 v1

本系统是本地研究和提醒工具，不接券商 API，不自动下单，不构成个性化投资建议。它会拉取免费日线市场数据，计算量化信号、质量股筛选、LOTS 仓位、风控退出条件和回测结果，并生成本地 HTML 报告或 Telegram/邮件摘要。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
bin/quant-ai-local run --config config/default.yaml --out outputs/latest_report.html
```

如果只想用离线合成数据验证报告链路：

```bash
bin/quant-ai-local run --config config/default.yaml --offline-sample --out outputs/sample_report.html
```

## 本地常驻服务

最简单的日常用法是启动本地网页服务：

```bash
cd /Users/heyisonl/Documents/量化投资系统
source .venv/bin/activate
bin/quant-ai-local serve --config config/default.yaml --out outputs/latest_report.html --open
```

浏览器会打开：

```text
http://127.0.0.1:8765
```

页面上可以点击：

- `刷新真实行情`：重新拉行情并生成最新报告；
- `打开完整报告`：查看完整信号、LOTS、Supervisor 审查和回测；
- `样本模式测试`：只测试系统链路，不代表真实交易信号。

如果希望登录 Mac 后自动启动服务：

```bash
bin/quant-ai-local install-service --config config/default.yaml --out outputs/latest_report.html
```

之后直接打开：

```bash
open http://127.0.0.1:8765
```

查看服务状态：

```bash
bin/quant-ai-local service-status
```

停止并移除开机/登录自启动：

```bash
bin/quant-ai-local uninstall-service
```

## Windows 主机部署

推荐使用 Docker 部署到 Windows 主机。Docker 方式见：

[docs/docker_deployment.md](docs/docker_deployment.md)

核心命令：

```powershell
docker compose build
docker compose up -d quant-ai-web
```

打开：

```text
http://127.0.0.1:8765
```

每日 Telegram 任务可以由 Windows Task Scheduler 调用：

```powershell
.\scripts\windows_docker_daily_job.ps1 -ProjectRoot "C:\path\to\hey-quant" -SendTelegram
```

从 GitHub 拉取新版本并重新部署：

```powershell
.\scripts\windows_docker_update.ps1 -ProjectRoot "C:\path\to\hey-quant"
```

也可以使用非 Docker 的 PowerShell 本地 Python 方式：

```powershell
cd C:\path\to\量化投资系统
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\bin\quant-ai-local.ps1 serve --config config\default.yaml --out outputs\latest_report.html --open
```

本地网页默认地址：

```text
http://127.0.0.1:8765
```

网页支持：

- 手动刷新真实行情；
- 打开完整报告；
- 新增/更新持仓；
- 记录买入、加仓、减仓、卖出；
- 标记清仓；
- 查看当前持仓和系统信号是否冲突。

Windows 非 Docker 定时邮件可以用 Task Scheduler。模板在：

```text
scripts/windows_daily_email_task.xml
```

使用前把 XML 里的 `__PROJECT_ROOT__` 替换成你的项目绝对路径，然后导入任务计划程序。默认时间是每天早上 07:30，本质上对应美股收盘后跑一次。

## 常用命令

```bash
# 生成今日扫描、仓位、风控和回测报告
bin/quant-ai-local run --config config/default.yaml

# 只看配置摘要
bin/quant-ai-local show-config --config config/default.yaml

# 运行回测并生成报告
bin/quant-ai-local backtest --config config/default.yaml --offline-sample

# 因子实验报告
bin/quant-ai-local factor-test --config config/default.yaml --offline-sample --out outputs/factor_report.html

# 生成报告并发送 Telegram
bin/quant-ai-local run --config config/default.yaml --out outputs/latest_report.html --send-telegram
```

## 模块

- `data`: yfinance 主数据源，Stooq 兜底，统一成复权 OHLCV。
- `indicators`: 均线、动量、RSI、ATR、相对强度。
- `quality`: “股神式”质量股覆盖层，按护城河、现金流、资本回报、资产负债表和估值纪律给手工质量分。
- `signals`: 技术分和质量分综合评分，默认技术 65%、质量 35%。
- `portfolio`: LOTS 仓位控制，按账户净值、目标权重和风险预算换算股数；默认集中到 1-2 个核心持仓。
- `portfolio_store`: SQLite 本地持仓和操作流水。
- `risk`: ATR 止损、50/200 日线退出、组合回撤和主题集中度检查。
- `supervisor`: GPT/本地规则主管审查层，最后复核数据质量、仓位、止损、杠杆 ETF 风险和执行前检查。
- `backtest`: 日线低频回测，包含滑点、下日成交和基准对比。
- `factors`: 单因子实验，用于学习和验证动量、相对强度、RSI 等因子的有效性。
- `telegram_notifier`: Telegram Bot 消息摘要。
- `emailer`: Outlook/SMTP 邮件摘要备用。
- `report`: 本地 HTML 报告。

更完整的架构和学习路线见：

[docs/architecture_and_learning_plan.md](docs/architecture_and_learning_plan.md)

项目里程碑和后续开发规划见：

[docs/milestones.md](docs/milestones.md)

本地开发流程和 GitHub 协作规则见：

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/development_workflow.md](docs/development_workflow.md)
- [docs/docker_deployment.md](docs/docker_deployment.md)
- [docs/windows_handoff.md](docs/windows_handoff.md)

## 当前默认策略

- 账户规模：140,000 HKD 按约 0.1276 汇率折为 17,870 USD。
- 持仓方式：不是日内平仓，默认做趋势持仓；当日只作为入场/加仓执行点，后续用周度/日线信号管理。
- 集中度：最多 2 个核心持仓，不把资金分散到太多股票。
- 普通股票：综合分 = 技术分 65% + 质量分 35%。
- 杠杆 ETF：`TQQQ`, `SOXL`, `USD` 只作为战术趋势工具，质量分低，初始仓位上限 10%，目标仓位上限 20%。
- 加仓逻辑：综合分高、趋势仍在、未触发风控时才进入核心候选。
- 减仓/退出：跌破 50 日线且相对强度转弱为减仓候选；跌破 200 日线为退出候选。

## AI / Supervisor 审查

默认启用 Supervisor 审查。它不会自动下单，而是把量化候选再过一遍“主管/投委会”检查：

- 数据是否是真实行情，是否有样本或过期数据；
- 技术信号和质量分是否同时达标；
- LOTS 仓位、止损价和风险预算是否完整；
- 杠杆 ETF 是否被降级为战术仓位；
- 最终输出 `approve_for_consideration`, `hold`, `reject`, `manual_review`。

AI 不负责拉行情、计算 MA/RSI/ATR、回测或替代止损；这些都由 Python 规则完成。AI 只做最后审查和解释。

默认 provider 是 DeepSeek，性价比优先：

```bash
export DEEPSEEK_API_KEY="你的DeepSeek key"
bin/quant-ai-local run --config config/default.yaml --out outputs/latest_report.html
```

也可以切换到 OpenAI：

```yaml
supervisor:
  provider: openai
  model: gpt-5.4-mini
```

然后设置：

```bash
export OPENAI_API_KEY="你的OpenAI key"
```

如果你希望没有 API key 时直接阻断，而不是本地规则兜底，把 `config/default.yaml` 里的：

```yaml
supervisor:
  require_api: true
```

## FMP 付费行情源

当前默认数据源已经改回免费优先：

```text
yfinance -> Stooq -> FMP
```

系统仍然支持读取本地 `.env` 里的 `FMP_API_KEY`：

```bash
FMP_API_KEY="你的FMP_API_KEY"
```

默认 `config/default.yaml` 里开启：

```yaml
data:
  stop_after_paid_provider: false
```

你暂时不付费 API 时，不需要设置 FMP key。以后接入付费源时，再把 `provider_priority` 和 `stop_after_paid_provider` 调整为付费源优先。

## Telegram 提醒

使用 Telegram Bot API。真实 token 只放在本机 `.env`，不要提交到 Git。

先给 bot 发送 `/start`，然后在 `.env` 里设置：

```text
TELEGRAM_BOT_TOKEN=你的BotFather token
TELEGRAM_CHAT_ID=你的chat id
```

如果不知道 chat id，先设置 `TELEGRAM_BOT_TOKEN`，然后运行：

```bash
bin/quant-ai-local telegram-chat-id --config config/default.yaml
```

发送命令：

```bash
bin/quant-ai-local run --config config/default.yaml --out outputs/latest_report.html --send-telegram
```

Telegram 会包含核心候选、持仓利润保护、风控候选、组合模式和数据质量提示。

## Outlook / SMTP 邮件备用

邮件配置通过环境变量读取，不写入代码：

```text
SMTP_USERNAME=你的Outlook邮箱
SMTP_PASSWORD=你的SMTP密码或应用密码
SMTP_FROM=你的Outlook邮箱
SMTP_TO=接收邮箱，可用逗号分隔多个
```

Windows 可以把这些放进 `.env` 文件。发送命令：

```powershell
.\bin\quant-ai-local.ps1 run --config config\default.yaml --out outputs\latest_report.html --send-email
```

邮件会包含核心候选、当前持仓检查、风控候选、Supervisor 审查和数据质量提示。

## 因子实验怎么理解

因子就是一个可以量化描述股票状态的指标，例如：

- `mom20`: 20日动量；
- `mom60`: 60日动量；
- `rel20`: 20日相对强度；
- `rel60`: 60日相对强度；
- `rsi14`: RSI。

因子实验会把股票按因子高低分组，然后看未来 20 个交易日收益：

```bash
bin/quant-ai-local factor-test --config config/default.yaml --out outputs/factor_report.html
```

如果 Top 分组未来收益明显高于 Bottom 分组，说明这个因子在当前样本里有区分度。这个结果只是研究工具，不是直接买卖信号。

## 默认股票池

`NVDA, AMD, AVGO, TSM, ASML, AMAT, LRCX, KLAC, MU, ARM, MRVL, SMCI, MSFT, GOOGL, META, AMZN, TSLA, PLTR, ORCL, ANET, VRT`

你可以在 `config/default.yaml` 里增删股票、调整账户净值、风险预算、滑点、股票池上限、主题暴露上限等参数。
