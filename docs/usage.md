# 使用说明

本文档是 Texas Hold'em Trainer 的本地运行和训练手册。README 只保留快速入口；安装细节、训练流程、AI 配置和排障统一维护在这里。

本项目仅用于本地单机训练和复盘，不提供真钱、支付、联网匹配或赌博功能。

## 1. 环境准备

需要：

- Python 3.11+
- Node.js 20+
- npm

安装后端依赖：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

安装前端依赖：

```bash
cd frontend
npm install
cd ..
```

## 2. 启动程序

推荐从仓库根目录一键启动：

```bash
./scripts/dev.sh
```

默认端口：

- 后端：`http://127.0.0.1:8001`
- 前端：`http://127.0.0.1:5173`

修改端口：

```bash
BACKEND_PORT=8002 FRONTEND_PORT=5174 ./scripts/dev.sh
```

脚本会自动设置 `PYTHONPATH=backend` 和 `VITE_PROXY_TARGET`。如果端口已被占用，脚本会打印占用进程并退出；先关闭旧进程，或换一个端口。

### 手动启动

后端：

```bash
PYTHONPATH="$PWD/backend" python -m uvicorn texas_holdem_trainer.api.app:app --reload --reload-dir "$PWD/backend" --port 8001
```

前端：

```bash
cd frontend
VITE_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5173 --strictPort
```

打开 Vite 输出的本地地址，例如 `http://127.0.0.1:5173`。

## 3. 第一次训练

1. 打开前端页面。
2. 在设置面板选择座位数、起始筹码、小盲、大盲和 AI 风格。
3. 点击创建牌桌。
4. 点击开始手牌。
5. 轮到真人玩家时，在行动区选择 `弃牌`、`过牌`、`跟注`、`下注`、`加注` 或 `全下`。
6. 对于下注和加注，可以输入具体金额；前端会先提示格式和范围错误，后端仍会做最终合法性校验。
7. 真人行动后，教练面板会显示评分、标签、建议行动和中文反馈。
8. AI 行动后，教练面板会显示动作、金额、风格、provider/model、置信度、fallback 状态和决策依据。
9. 历史面板会持续记录盲注、发牌、行动、复盘、街道推进、摊牌和结算事件。

## 4. 界面区域

### 牌桌

展示座位、筹码、当前下注、底池、公共牌、真人手牌、庄位、小盲、大盲和当前行动玩家。AI 手牌在未摊牌前保持隐藏。

### 行动区

行动区只展示后端返回的合法动作。前端负责交互提示，不能替代后端规则判断。

- `弃牌`：放弃当前手牌。
- `过牌`：无人下注时不投入筹码。
- `跟注`：补齐到当前最高下注。
- `下注`：无人下注时主动投入筹码。
- `加注`：把当前最高下注提高到指定总额。
- `全下`：投入当前剩余筹码。

### 教练面板

展示两类信息：

- AI 决策：动作、金额、风格、决策源、模型、置信度和公开理由。
- 真人复盘：本次行动评分、评价标签、建议行动和即时反馈。

公开理由不会泄露其他玩家隐藏手牌。LLM 原始输出会经过后端解析和整理；非法动作、非法金额或非法复盘结构都会触发 fallback。

### 历史面板

按时间顺序展示当前手牌事件，用于复盘行动链和结算结果。

## 5. AI 玩家配置

默认不需要 API key，AI 会使用本地 heuristic provider。

复制配置：

```bash
cp .env.example .env
cp config/ai_players.example.yaml config/ai_players.yaml
```

`.env` 常用项：

```text
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
LLM_TIMEOUT_SECONDS=12
AI_PLAYERS_CONFIG=config/ai_players.yaml
AI_DEFAULT_PROVIDER=heuristic
```

`config/ai_players.yaml` 中每个 profile 可以配置名称、风格、provider 和模型：

```yaml
profiles:
  - name: "TAG Bot"
    style: "tight_aggressive"
    provider: "openai"
```

当前风格：

- `tight_aggressive`：紧凶，范围更紧，强牌更主动。
- `loose_aggressive`：松凶，范围更宽，进攻频率更高。
- `conservative`：保守，更倾向控池和弃弱牌。
- `bluff_heavy`：诈唬型，更愿意用进攻施压。
- `gto_leaning`：GTO 倾向，参数更均衡。

profile 的 `name` 用于前端展示、日志和复盘识别。建议保持唯一，避免排查日志时混淆。

## 6. 真人复盘教练

真人行动复盘由 `reviewer` 配置决定，和电脑玩家 profile 独立：

```yaml
reviewer:
  provider: "heuristic"
```

可切换为 LLM provider：

```yaml
reviewer:
  provider: "openai"
  model: "gpt-4.1"
```

复盘 provider 只评价已提交行动是否合理，并给出训练建议。它不会改变已发生的动作，也不能影响合法动作校验和筹码结算。

## 7. Codex app-server provider

如果本机已登录 Codex，可以通过 `codex_app` provider 使用 Codex app-server/native runtime。该方式不需要把 OpenAI API key 配给本应用，但后端进程必须能访问当前用户的 Codex 登录状态。

示例：

```yaml
providers:
  codex_app:
    runtime: "codex_app_server"
    command: "codex"
    model: "gpt-5.5"
    timeout_seconds: 60

profiles:
  - name: "GTO Bot"
    style: "gto_leaning"
    provider: "codex_app"

reviewer:
  provider: "codex_app"
  model: "gpt-5.5"
```

后端会启动本地 `codex app-server --listen stdio://` 子进程，并通过 JSON-RPC 发送可见牌局状态。Codex 只负责返回动作建议、中文理由或复盘结果；后端继续校验所有规则。

## 8. 规则边界

以下规则必须由代码执行，不能依赖 LLM：

- 洗牌和发牌。
- 小盲和大盲。
- 行动顺序。
- 合法动作校验。
- check/call/bet/raise/fold/all-in。
- 每轮下注状态。
- flop/turn/river 流程。
- showdown 胜负判断。
- MVP 简化 all-in 结算。
- 筹码结算。
- hand history。

LLM 只负责“如何选择动作”和“为什么这么选择”，以及对真人行动给出训练反馈。

## 9. 验证命令

后端和规则测试：

```bash
python -m pytest -q
```

前端类型检查和构建：

```bash
cd frontend
npm run build
```

推荐手动烟测：

1. 创建牌桌。
2. 开始手牌。
3. 确认真人手牌和合法动作显示。
4. 输入一个合法加注金额并提交。
5. 确认 AI 行动继续推进。
6. 确认教练面板展示 AI reasoning 和真人复盘。
7. 确认历史事件持续增加。

## 10. 常见问题

### 端口已被占用

`./scripts/dev.sh` 会显示占用进程。关闭旧后端/前端进程，或换端口启动：

```bash
BACKEND_PORT=8002 FRONTEND_PORT=5174 ./scripts/dev.sh
```

### 前端显示 API 请求失败

确认后端正在运行，并且 `VITE_PROXY_TARGET` 指向正确后端端口。使用 `./scripts/dev.sh` 时会自动设置。

### 前端构建提示 `tsc: command not found`

说明前端依赖未安装：

```bash
cd frontend
npm install
npm run build
```

### LLM 没有生效

检查：

- `.env` 是否存在。
- API key 环境变量是否有值。
- `AI_PLAYERS_CONFIG` 是否指向正确 YAML。
- YAML 中 profile/provider 是否配置正确。
- 后端是否已重启。

provider 缺少 key、超时、返回非法 JSON、返回非法动作或非法金额时，后端会 fallback 到 heuristic provider。

### 为什么不是完整 side pot

当前 MVP 支持简化 all-in 处理。完整 side pot 创建和结算是后续里程碑；结算逻辑已经集中在后端 engine，后续可以增强而不改变 UI 和 AI 决策接口。
