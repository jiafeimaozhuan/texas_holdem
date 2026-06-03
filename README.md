# Texas Hold'em Trainer

本项目是一个本地单机德州扑克训练程序，用于日常练习牌局决策。一个真实人类玩家可以与多个可配置风格的 AI 玩家同桌训练；后端负责确定性规则执行，LLM 只负责 AI 决策建议、决策理由和人类行动复盘。

项目不支持真钱、支付、联网匹配或赌博流程。

## 功能概览

- 支持 2-9 人训练桌，其中 1 个座位为真人玩家。
- 后端实现洗牌、发牌、盲注、行动顺序、合法动作校验、下注轮、flop/turn/river、showdown、筹码结算和 hand history。
- AI 支持本地 heuristic、OpenAI-compatible provider、DeepSeek provider 和 Codex app-server provider。
- 每个 AI 玩家可配置紧凶、松凶、保守、诈唬型、GTO 倾向等风格。
- 前端展示牌桌、玩家筹码、公共牌、手牌、下注动作、底池、行动顺序、AI 思考过程和真人行动复盘。
- MVP all-in/side pot 仍为简化实现，完整 side pot 是后续里程碑。

## 项目结构

```text
backend/texas_holdem_trainer/  FastAPI、运行时、AI provider、德州扑克规则引擎
frontend/src/                  React/Vite 前端源码
tests/                         pytest 测试
config/                        AI 玩家和 provider 配置
docs/                          使用说明、设计文档和实施计划
scripts/dev.sh                 本地一键启动脚本
```

## 快速开始

环境要求：Python 3.11+、Node.js 20+、npm。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cd frontend
npm install
cd ..
./scripts/dev.sh
```

默认启动地址：

- 后端：`http://127.0.0.1:8001`
- 前端：`http://127.0.0.1:5173`

如需改端口：

```bash
BACKEND_PORT=8002 FRONTEND_PORT=5174 ./scripts/dev.sh
```

## 文档

- [使用说明](docs/usage.md)：安装、启动、首次训练、界面说明、AI/LLM 配置、验证命令和常见问题。
- [设计文档](docs/superpowers/specs/2026-05-24-texas-holdem-trainer-design.md)：产品范围、核心规则边界和架构设计。
- [实施计划](docs/superpowers/plans/2026-05-24-texas-holdem-trainer-implementation.md)：MVP 实现步骤和后续迭代方向。
- [贡献指南](AGENTS.md)：给维护者和 coding agent 的仓库约定。

## 验证

```bash
python -m pytest -q
cd frontend
npm run build
```

## 配置与安全

真实 API key 放在本地 `.env`，不要提交到 Git。可复制 `.env.example` 和 `config/ai_players.example.yaml` 开始配置。

LLM 不能决定规则结果。合法动作、下注金额、胜负、筹码结算和 hand history 始终由后端代码校验和执行。

## License

MIT License. See [LICENSE](LICENSE).
