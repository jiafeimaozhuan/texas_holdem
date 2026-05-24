# Texas Hold'em Trainer 使用说明

本文档说明如何在本地运行德州扑克训练程序、如何开始一局训练、如何配置 AI 玩家，以及如何查看 AI 决策依据。

本项目只用于本地单机训练和复盘，不提供真钱、支付、联网匹配或赌博功能。

## 1. 环境要求

- Python 3.11+
- Node.js 20+
- npm

建议在项目根目录执行后端命令，在 `frontend/` 目录执行前端命令。

## 2. 安装依赖

后端：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

前端：

```bash
cd frontend
npm install
```

## 3. 启动程序

启动后端：

```bash
source .venv/bin/activate
PYTHONPATH=backend python -m uvicorn texas_holdem_trainer.api.app:app --reload --reload-dir backend --port 8000
```

启动前端：

```bash
cd frontend
npm run dev
```

浏览器打开 Vite 输出的地址，通常是：

```text
http://127.0.0.1:5173
```

如果本机 `8000` 端口已被占用，可以改用备用端口：

```bash
PYTHONPATH=backend python -m uvicorn texas_holdem_trainer.api.app:app --reload --reload-dir backend --port 8001
cd frontend
VITE_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

## 4. 第一次训练流程

1. 打开前端页面。
2. 在右侧 `Settings` 面板设置座位数、起始筹码、小盲和大盲。
3. 为每个 AI 玩家选择风格，例如 Tight Aggressive、Loose Aggressive、Conservative、Bluff Heavy、GTO Leaning。
4. 点击 `Create Table` 创建训练桌。
5. 点击 `Start Hand` 开始一手牌。
6. 轮到人类玩家时，底部 `Actions` 面板会显示后端返回的合法动作。
7. 点击 `Fold`、`Check`、`Call`、`Bet`、`Raise` 或 `All-in` 完成行动。
8. AI 行动后，右侧 `Coach` 面板会显示 AI 的动作、下注额、风格、provider/model、置信度和决策依据。
9. `History` 面板会记录盲注、发牌、行动、街道推进、AI 决策和结算事件。

## 5. 界面说明

### Table

牌桌区域展示：

- 玩家座位、名称和筹码。
- 人类玩家手牌。
- AI 玩家隐藏手牌，摊牌或手牌结束后按后端状态展示。
- 公共牌。
- 底池、当前下注、最小加注。
- Dealer、SB、BB 和当前行动玩家标记。

### Actions

行动区只展示后端判定为合法的动作。前端不会自行判断德州扑克规则。

- `Fold`：弃牌。
- `Check`：无人下注时过牌。
- `Call`：跟注到当前下注额。
- `Bet`：无人下注时主动下注。
- `Raise`：加注到指定总额。
- `All-in`：投入当前剩余筹码。

`Bet`、`Raise` 和 `All-in` 会显示金额输入框。即使可选金额固定，界面也会展示金额，方便复盘时看清提交数值。

### Coach

Coach 面板展示最近一次 AI 决策：

- AI 玩家名称。
- 风格。
- provider 和 model。
- 动作和金额。
- confidence。
- fallback 状态。
- 面向人类复盘的公开决策说明。

公开说明不会直接显示其他玩家的隐藏手牌。LLM 原始输出不会直接作为公开说明使用，后端会生成安全的公开说明模板。

### History

History 面板按时间顺序展示当前手牌事件：

- hand started。
- small blind / big blind。
- hole cards dealt。
- 玩家行动。
- AI decision。
- street transition。
- showdown / settlement。

## 6. AI 玩家风格

当前支持的风格：

- `tight_aggressive`：紧凶，入池范围更紧，强牌更主动。
- `loose_aggressive`：松凶，入池更宽，进攻频率更高。
- `conservative`：保守，更倾向控池和弃弱牌。
- `bluff_heavy`：诈唬型，更愿意用进攻施压。
- `gto_leaning`：GTO 倾向，参数更均衡。

这些风格会影响 heuristic provider 的风险偏好、诈唬频率和进攻倾向，也会作为 LLM provider 的输入上下文。

## 7. LLM Provider 配置

不配置 API key 时，程序默认使用本地 heuristic AI，可以离线训练。

如需尝试 OpenAI-compatible LLM provider：

1. 复制环境变量示例：

```bash
cp .env.example .env
```

2. 编辑 `.env`：

```text
OPENAI_API_KEY=your-openai-key
DEEPSEEK_API_KEY=your-deepseek-key
LLM_TIMEOUT_SECONDS=12
AI_PLAYERS_CONFIG=config/ai_players.yaml
AI_DEFAULT_PROVIDER=heuristic
```

3. 复制 AI 配置示例：

```bash
cp config/ai_players.example.yaml config/ai_players.yaml
```

4. 在 `config/ai_players.yaml` 中把某个 profile 的 provider 改为 `openai` 或 `deepseek`：

```yaml
profiles:
  - name: "TAG Bot"
    style: "tight_aggressive"
    provider: "openai"
```

也可以设置：

```text
AI_DEFAULT_PROVIDER=openai
```

这会让没有显式 profile override 的风格默认使用 OpenAI provider。

如果 provider 缺少 API key、超时、返回非法 JSON、返回非法动作或金额，后端会自动 fallback 到 heuristic provider，并在 Coach/History 中记录 fallback 状态。

## 8. 规则边界

德州扑克核心规则由代码实现，不依赖 LLM 判断：

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

LLM 只负责 AI 玩家“选择哪个后端合法动作”和“为什么这么选”。即使 LLM 给出非法动作，后端也会拒绝并 fallback。

## 9. 验证命令

后端测试：

```bash
python -m pytest -q
```

前端构建：

```bash
cd frontend
npm run build
```

推荐手动烟测：

1. Create Table。
2. Start Hand。
3. 确认 Hero 手牌和合法动作显示。
4. 提交一个动作。
5. 确认 AI 行动继续推进。
6. 确认 Coach 展示 AI reasoning。
7. 确认 History 事件增加。

## 10. 常见问题

### 前端显示 API 请求失败

确认后端正在运行，并且 Vite proxy 指向正确端口。

默认情况下前端代理到：

```text
http://127.0.0.1:8000
```

如果后端使用 `8001`，启动前端时需要：

```bash
VITE_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

### 前端构建提示 `tsc: command not found`

说明 `frontend/node_modules` 不存在或依赖未安装：

```bash
cd frontend
npm install
npm run build
```

### LLM 没有生效

检查：

- `.env` 是否存在。
- API key 对应的环境变量是否有值。
- `AI_PLAYERS_CONFIG` 是否指向正确 YAML。
- YAML 中 profile/provider 是否设置为 `openai` 或 `deepseek`。
- 后端是否已重启。

没有可用 key 时，provider 会被跳过，界面会显示 heuristic/local。

### 为什么不是完整 side pot

MVP 支持简化 all-in 处理，完整 side-pot 创建和结算是后续里程碑。当前代码已经把结算逻辑集中在后端 engine，后续可以替换/增强而不改变 UI 和 AI 决策接口。
