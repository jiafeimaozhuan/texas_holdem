from __future__ import annotations

import asyncio
import json
import logging
import shlex
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Mapping, Protocol, Sequence

import httpx

from texas_holdem_trainer.ai.profiles import BotProfile, BotStyle
from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Card
from texas_holdem_trainer.domain.evaluator import HandCategory, evaluate_best
from texas_holdem_trainer.domain.state import GameState


logger = logging.getLogger(__name__)


_CODEX_STDOUT_READ_CHUNK_BYTES = 65_536
_CODEX_STDOUT_MAX_LINE_BYTES = 10_000_000


def _emit_llm_log(message: str) -> None:
    logger.info(message)
    print(message, flush=True)


def _compact_response_text(response: httpx.Response) -> str:
    try:
        return json.dumps(response.json(), ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        return response.text


@dataclass(frozen=True)
class DecisionResult:
    action: ActionType
    amount: int = 0
    confidence: float = 0.5
    reasoning: str = ""
    source_reasoning: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None


@dataclass(frozen=True)
class HumanReviewResult:
    score: int
    label: str
    reasoning: str
    suggested_action: ActionType | None = None
    suggested_amount: int | None = None
    provider: str = "heuristic"
    model: str = "local"
    fallback_used: bool = False
    fallback_reason: str | None = None


class AIProvider(Protocol):
    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        ...

    async def review_human_action(
        self,
        state: GameState,
        seat: int,
        legal_actions: Sequence[LegalAction],
        action: ActionType,
        amount: int,
        visible_state: Mapping[str, Any] | None = None,
    ) -> HumanReviewResult:
        ...


class HeuristicProvider:
    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        if not legal_actions:
            raise ValueError("legal_actions must not be empty")

        legal_by_type = {action.type: action for action in legal_actions}
        player = state.players[seat]
        strength = _hand_strength([*player.hole_cards, *state.board])

        if ActionType.CALL in legal_by_type:
            return self._facing_bet_decision(
                state,
                profile,
                legal_by_type,
                strength,
            )

        return self._no_bet_decision(profile, legal_by_type, strength)

    def _facing_bet_decision(
        self,
        state: GameState,
        profile: BotProfile,
        legal_by_type: dict[ActionType, LegalAction],
        strength: float,
    ) -> DecisionResult:
        call_action = legal_by_type[ActionType.CALL]
        call_amount = call_action.min_amount
        pot_after_call = max(1, state.pot + call_amount)
        pot_odds = call_amount / pot_after_call
        continue_threshold = max(0.18, pot_odds - profile.risk_tolerance * 0.15)
        pressure = call_amount / max(1, state.pot + call_amount)

        can_raise = ActionType.RAISE in legal_by_type
        should_pressure = (
            can_raise
            and strength >= 0.68
            and profile.aggression >= 0.55
        ) or (
            can_raise
            and strength >= 0.48
            and profile.aggression + profile.bluff_frequency >= 0.95
        )
        if should_pressure:
            raise_action = legal_by_type[ActionType.RAISE]
            amount = _scaled_amount(raise_action, profile.aggression)
            return DecisionResult(
                action=ActionType.RAISE,
                amount=amount,
                confidence=min(0.95, 0.55 + strength * 0.35),
                reasoning="raising with enough hand strength and profile aggression",
            )

        if strength >= continue_threshold or (strength >= 0.42 and pressure <= 0.28):
            return DecisionResult(
                action=ActionType.CALL,
                amount=call_amount,
                confidence=min(0.9, 0.45 + strength * 0.35),
                reasoning="calling because hand strength or pot odds justify continuing",
            )

        if ActionType.FOLD in legal_by_type:
            return DecisionResult(
                action=ActionType.FOLD,
                confidence=min(0.9, 0.45 + pressure),
                reasoning="folding weak hand against a large price",
            )

        return _first_legal_decision(legal_by_type, "using only available legal action")

    def _no_bet_decision(
        self,
        profile: BotProfile,
        legal_by_type: dict[ActionType, LegalAction],
        strength: float,
    ) -> DecisionResult:
        can_bet = ActionType.BET in legal_by_type
        value_bet = can_bet and strength >= max(0.58, 0.82 - profile.aggression * 0.25)
        pressure_bet = (
            can_bet
            and strength >= 0.44
            and profile.aggression + profile.bluff_frequency >= 1.0
        )
        if value_bet or pressure_bet:
            bet_action = legal_by_type[ActionType.BET]
            amount = _scaled_amount(bet_action, profile.aggression)
            return DecisionResult(
                action=ActionType.BET,
                amount=amount,
                confidence=min(0.9, 0.5 + strength * 0.3),
                reasoning="betting because profile aggression supports pressure",
            )

        if ActionType.CHECK in legal_by_type:
            return DecisionResult(
                action=ActionType.CHECK,
                confidence=0.65,
                reasoning="checking when no bet is faced",
            )

        return _first_legal_decision(legal_by_type, "using first backend legal action")

    async def review_human_action(
        self,
        state: GameState,
        seat: int,
        legal_actions: Sequence[LegalAction],
        action: ActionType,
        amount: int,
        visible_state: Mapping[str, Any] | None = None,
    ) -> HumanReviewResult:
        recommended = await self.decide(
            state,
            seat,
            BotProfile.for_style("human-review", BotStyle.GTO_LEANING),
            legal_actions,
            visible_state=visible_state,
        )
        same_action = recommended.action is action
        amount_close = (
            action in {ActionType.FOLD, ActionType.CHECK}
            or abs(recommended.amount - amount) <= max(10, int(max(1, recommended.amount) * 0.25))
        )
        if same_action and amount_close:
            score = 88
            label = "优秀"
            reasoning = "你的行动接近本地基准建议，下注尺寸也在合理范围内。"
        elif same_action:
            score = 74
            label = "可接受"
            reasoning = "行动方向合理，但下注尺寸可以再贴近底池压力和最小加注要求。"
        elif action is ActionType.FOLD and recommended.action in {ActionType.CALL, ActionType.CHECK}:
            score = 58
            label = "偏紧"
            reasoning = "这次弃牌偏保守，本地基准认为继续看牌或跟注仍有可接受价值。"
        elif action in {ActionType.CALL, ActionType.BET, ActionType.RAISE, ActionType.ALL_IN} and recommended.action is ActionType.FOLD:
            score = 42
            label = "风险过高"
            reasoning = "这次投入偏冒进，本地基准认为当前牌力或价格不足以继续。"
        else:
            score = 64
            label = "可接受"
            reasoning = "这次行动不算明显错误，但和本地基准建议不同，建议复盘位置、赔率和下注压力。"
        return HumanReviewResult(
            score=score,
            label=label,
            reasoning=reasoning,
            suggested_action=recommended.action,
            suggested_amount=recommended.amount,
        )


class LLMProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport

    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        payload = {
            "model": profile.model or self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Choose exactly one backend-provided Texas Hold'em legal "
                        "action. Return strict JSON only. Write reasoning in Chinese."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "profile": {
                                "name": profile.name,
                                "style": profile.style.value,
                                "risk_tolerance": profile.risk_tolerance,
                                "bluff_frequency": profile.bluff_frequency,
                                "aggression": profile.aggression,
                            },
                            "visible_state": visible_state,
                            "legal_actions": [
                                {
                                    "action": action.type.value,
                                    "min_amount": action.min_amount,
                                    "max_amount": action.max_amount,
                                }
                                for action in legal_actions
                            ],
                            "required_json_schema": {
                                "action": "fold|check|call|bet|raise|all_in",
                                "amount": "integer",
                                "confidence": "number between 0 and 1",
                                "reasoning": "short Chinese string",
                            },
                        },
                        separators=(",", ":"),
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_url = f"{self.base_url}/chat/completions"
        _emit_llm_log(
            "LLM request "
            f"url={request_url} "
            f"model={payload['model']} "
            f"payload={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                request_url,
                json=payload,
                headers=headers,
            )
            _emit_llm_log(
                "LLM response "
                f"url={request_url} "
                f"status={response.status_code} "
                f"body={_compact_response_text(response)}"
            )
            response.raise_for_status()

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("LLM response missing message content") from exc
        return self._parse_content(content)

    async def review_human_action(
        self,
        state: GameState,
        seat: int,
        legal_actions: Sequence[LegalAction],
        action: ActionType,
        amount: int,
        visible_state: Mapping[str, Any] | None = None,
    ) -> HumanReviewResult:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Evaluate a human Texas Hold'em action for training. "
                        "Return strict JSON only. Write reasoning in Chinese. "
                        "Do not claim hidden opponent cards."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        _human_review_prompt_payload(
                            visible_state,
                            legal_actions,
                            action,
                            amount,
                        ),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_url = f"{self.base_url}/chat/completions"
        _emit_llm_log(
            "LLM review request "
            f"url={request_url} "
            f"model={payload['model']} "
            f"payload={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                request_url,
                json=payload,
                headers=headers,
            )
            _emit_llm_log(
                "LLM review response "
                f"url={request_url} "
                f"status={response.status_code} "
                f"body={_compact_response_text(response)}"
            )
            response.raise_for_status()

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("LLM review response missing message content") from exc
        return _parse_review_json(content, "LLM review response", "llm", self.model)

    def _parse_content(self, content: str) -> DecisionResult:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM response content is not strict JSON") from exc

        required_keys = {"action", "amount", "confidence", "reasoning"}
        if not isinstance(parsed, dict):
            raise ValueError("LLM response JSON must be an object")
        if set(parsed) != required_keys:
            raise ValueError("LLM response JSON must contain exactly required keys")

        action_value = parsed["action"]
        amount = parsed["amount"]
        confidence = parsed["confidence"]
        reasoning = parsed["reasoning"]

        if not isinstance(action_value, str):
            raise ValueError("LLM action must be a string")
        try:
            action = ActionType(action_value)
        except ValueError as exc:
            raise ValueError("LLM action is not supported") from exc

        if not isinstance(amount, int) or isinstance(amount, bool):
            raise ValueError("LLM amount must be an integer")
        if (
            not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("LLM confidence must be a number between 0 and 1")
        if not isinstance(reasoning, str):
            raise ValueError("LLM reasoning must be a string")

        return DecisionResult(
            action=action,
            amount=amount,
            confidence=float(confidence),
            reasoning=reasoning,
        )


class CodexAppServerProvider:
    def __init__(
        self,
        *,
        model: str = "gpt-5.5",
        command: str = "codex",
        timeout: float = 60.0,
        cwd: str | None = None,
        client: "CodexAppServerClient | None" = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.client = client or CodexAppServerClient(command=command, cwd=cwd)

    async def decide(
        self,
        state: GameState,
        seat: int,
        profile: BotProfile,
        legal_actions: Sequence[LegalAction],
        visible_state: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        prompt = _codex_decision_prompt(profile, visible_state, legal_actions)
        model = profile.model or self.model
        thread_key = f"decision:{model}"
        last_error: ValueError | None = None
        for attempt in range(2):
            attempt_prompt = prompt
            if last_error is not None:
                attempt_prompt = (
                    f"{prompt}\n\n上一轮返回无效：{last_error}。"
                    "请重新返回严格 JSON，且只返回 JSON 对象。"
                )
            _emit_llm_log(
                "Codex app-server request "
                f"model={model} "
                f"thread_key={thread_key} "
                f"prompt={attempt_prompt}"
            )
            content = await self.client.complete(
                prompt=attempt_prompt,
                model=model,
                output_schema=_DECISION_OUTPUT_SCHEMA,
                thread_key=thread_key,
                timeout=self.timeout,
            )
            _emit_llm_log(
                "Codex app-server response "
                f"model={model} "
                f"thread_key={thread_key} "
                f"body={content}"
            )
            try:
                return _parse_decision_json(content, "Codex app-server response")
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "Codex app-server returned invalid decision JSON on attempt %s: %s",
                    attempt + 1,
                    content,
                    exc_info=exc,
                )
        if last_error is None:
            raise ValueError("Codex app-server response could not be parsed")
        raise last_error

    async def review_human_action(
        self,
        state: GameState,
        seat: int,
        legal_actions: Sequence[LegalAction],
        action: ActionType,
        amount: int,
        visible_state: Mapping[str, Any] | None = None,
    ) -> HumanReviewResult:
        model = self.model
        prompt = _codex_review_prompt(visible_state, legal_actions, action, amount)
        thread_key = f"review:{model}"
        last_error: ValueError | None = None
        for attempt in range(2):
            attempt_prompt = prompt
            if last_error is not None:
                attempt_prompt = (
                    f"{prompt}\n\n上一轮返回无效：{last_error}。"
                    "请重新返回严格 JSON，且只返回 JSON 对象。"
                )
            _emit_llm_log(
                "Codex app-server review request "
                f"model={model} "
                f"thread_key={thread_key} "
                f"prompt={attempt_prompt}"
            )
            content = await self.client.complete(
                prompt=attempt_prompt,
                model=model,
                output_schema=_REVIEW_OUTPUT_SCHEMA,
                thread_key=thread_key,
                timeout=self.timeout,
            )
            _emit_llm_log(
                "Codex app-server review response "
                f"model={model} "
                f"thread_key={thread_key} "
                f"body={content}"
            )
            try:
                return _parse_review_json(
                    content,
                    "Codex app-server review response",
                    "codex_app",
                    model,
                )
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "Codex app-server returned invalid review JSON on attempt %s: %s",
                    attempt + 1,
                    content,
                    exc_info=exc,
                )
        if last_error is None:
            raise ValueError("Codex app-server review response could not be parsed")
        raise last_error

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            result = close()
            if isawaitable(result):
                await result


class CodexAppServerClient:
    def __init__(
        self,
        *,
        command: str = "codex",
        cwd: str | None = None,
        max_turns_per_process: int = 16,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.max_turns_per_process = max(1, max_turns_per_process)
        self.process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()
        self._thread_ids: dict[str, str] = {}
        self._stderr_task: asyncio.Task[None] | None = None
        self._turns_started = 0
        self._stdout_buffer = b""

    async def close(self) -> None:
        process = self.process
        self.process = None
        self._thread_ids.clear()
        self._stdout_buffer = b""
        stderr_task = self._stderr_task
        self._stderr_task = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        if stderr_task is not None:
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
        self._turns_started = 0

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict,
        thread_key: str,
        timeout: float,
    ) -> str:
        async with self._lock:
            try:
                return await asyncio.wait_for(
                    self._complete_locked(
                        prompt=prompt,
                        model=model,
                        output_schema=output_schema,
                        thread_key=thread_key,
                    ),
                    timeout=timeout,
                )
            except TimeoutError:
                await self.close()
                raise
            except asyncio.CancelledError:
                await self.close()
                raise
            except (RuntimeError, ValueError):
                await self.close()
                raise

    async def _complete_locked(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict,
        thread_key: str,
    ) -> str:
        await self._ensure_process()
        if self._turns_started >= self.max_turns_per_process:
            await self.close()
            await self._ensure_process()
        thread_id = await self._thread_id(thread_key, model)
        try:
            return await self._start_turn_and_wait(
                thread_id=thread_id,
                model=model,
                prompt=prompt,
                output_schema=output_schema,
            )
        finally:
            self._turns_started += 1

    async def _start_turn_and_wait(
        self,
        *,
        thread_id: str,
        model: str,
        prompt: str,
        output_schema: dict,
    ) -> str:
        request_id = self._next_id
        self._next_id += 1
        await self._write_message(
            {
                "id": request_id,
                "method": "turn/start",
                "params": {
                    "threadId": thread_id,
                    "model": model,
                    "input": [{"type": "text", "text": prompt}],
                    "outputSchema": output_schema,
                    "approvalPolicy": "never",
                    "environments": [],
                },
            }
        )

        while True:
            message = await self._read_message()
            if message.get("id") == request_id:
                if "error" in message:
                    raise ValueError(f"Codex app-server turn/start failed: {message['error']}")
                result = message.get("result")
                text = _extract_final_message(
                    result.get("turn") if isinstance(result, dict) else None
                )
                if text:
                    return text
                continue
            if message.get("method") == "turn/completed":
                params = message.get("params")
                if isinstance(params, dict) and params.get("threadId") == thread_id:
                    turn = params.get("turn")
                    _raise_if_turn_failed(turn)
                    text = _extract_final_message(turn)
                    if text:
                        return text
                    turn_id = turn.get("id") if isinstance(turn, dict) else None
                    if isinstance(turn_id, str):
                        text = await self._read_completed_turn_message(
                            thread_id=thread_id,
                            turn_id=turn_id,
                        )
                        if text:
                            return text
                    raise ValueError("Codex app-server turn completed without final message")

    async def _read_completed_turn_message(self, *, thread_id: str, turn_id: str) -> str | None:
        for attempt in range(5):
            response = await self._request(
                "thread/read",
                {
                    "threadId": thread_id,
                    "includeTurns": True,
                },
            )
            if isinstance(response, dict):
                thread = response.get("thread")
                if isinstance(thread, dict):
                    turns = thread.get("turns")
                    if isinstance(turns, list):
                        for turn in reversed(turns):
                            if isinstance(turn, dict) and turn.get("id") == turn_id:
                                _raise_if_turn_failed(turn)
                                text = _extract_final_message(turn)
                                if text:
                                    return text
            if attempt < 4:
                await asyncio.sleep(0.2)
        return None

    async def _thread_id(self, thread_key: str, model: str) -> str:
        thread_id = self._thread_ids.get(thread_key)
        if thread_id:
            return thread_id
        response = await self._request(
            "thread/start",
            {
                "model": model,
                "ephemeral": False,
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "environments": [],
                "baseInstructions": (
                    "You are a Texas Hold'em decision engine. Do not use tools. "
                    "Return only the requested JSON object."
                ),
                "cwd": self.cwd,
            },
        )
        if not isinstance(response, dict):
            raise ValueError("Codex app-server thread/start returned malformed result")
        thread = response.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise ValueError("Codex app-server thread/start missing thread id")
        thread_id = thread["id"]
        self._thread_ids[thread_key] = thread_id
        return thread_id

    async def _ensure_process(self) -> None:
        if self.process and self.process.returncode is None:
            return
        args = [*shlex.split(self.command), "app-server", "--listen", "stdio://"]
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "texas-holdem-trainer",
                    "version": "0.1",
                },
                "capabilities": {
                    "experimentalApi": True,
                },
            },
        )
        await self._notify("initialized")

    async def _drain_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        while True:
            line = await process.stderr.readline()
            if not line:
                return
            logger.debug("Codex app-server stderr: %s", line.decode(errors="replace").rstrip())

    async def _request(self, method: str, params: Mapping[str, Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        await self._write_message(
            {
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        while True:
            message = await self._read_message()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise ValueError(f"Codex app-server {method} failed: {message['error']}")
            return message.get("result")

    async def _notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        await self._write_message(message)

    async def _write_message(self, message: Mapping[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None:
            raise RuntimeError("Codex app-server process is not running")
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
        process.stdin.write(line + b"\n")
        await process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        process = self.process
        if process is None or process.stdout is None:
            raise RuntimeError("Codex app-server process is not running")
        pending = ""
        pending_lines = 0
        while True:
            line = await self._read_stdout_line()
            if not line:
                raise ValueError("Codex app-server process closed stdout")
            raw_line = line.decode(errors="replace").rstrip("\n").rstrip("\r")
            stripped = raw_line.strip()
            if not stripped:
                continue
            candidate = f"{pending}\n{raw_line}" if pending else stripped
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                if (
                    _should_buffer_json_parse_failure(candidate.strip(), exc)
                    and len(candidate) <= 1_000_000
                    and pending_lines < 1_000
                ):
                    pending = candidate
                    pending_lines += 1
                    continue
                logger.warning(
                    "Failed to parse Codex app-server stdout message: %s",
                    _preview_line(candidate),
                    exc_info=exc,
                )
                pending = ""
                pending_lines = 0
                continue
            if not isinstance(parsed, dict):
                raise ValueError("Codex app-server returned non-object JSON-RPC message")
            return parsed

    async def _read_stdout_line(self) -> bytes:
        process = self.process
        if process is None or process.stdout is None:
            raise RuntimeError("Codex app-server process is not running")

        while b"\n" not in self._stdout_buffer:
            chunk = await process.stdout.read(_CODEX_STDOUT_READ_CHUNK_BYTES)
            if not chunk:
                line = self._stdout_buffer
                self._stdout_buffer = b""
                return line
            self._stdout_buffer += chunk
            if len(self._stdout_buffer) > _CODEX_STDOUT_MAX_LINE_BYTES:
                raise ValueError("Codex app-server stdout message exceeded maximum line length")

        line, self._stdout_buffer = self._stdout_buffer.split(b"\n", 1)
        return line + b"\n"


_DECISION_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["action", "amount", "confidence", "reasoning"],
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": ["fold", "check", "call", "bet", "raise", "all_in"]},
        "amount": {"type": "integer", "minimum": 0},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
    },
}


_REVIEW_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["score", "label", "reasoning", "suggested_action", "suggested_amount"],
    "additionalProperties": False,
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "label": {
            "type": "string",
            "enum": ["优秀", "可接受", "偏松", "偏紧", "风险过高"],
        },
        "reasoning": {"type": "string"},
        "suggested_action": {
            "type": ["string", "null"],
            "enum": ["fold", "check", "call", "bet", "raise", "all_in", None],
        },
        "suggested_amount": {"type": ["integer", "null"], "minimum": 0},
    },
}


def _human_review_prompt_payload(
    visible_state: Mapping[str, Any] | None,
    legal_actions: Sequence[LegalAction],
    action: ActionType,
    amount: int,
) -> dict[str, Any]:
    return {
        "task": "review_human_action",
        "visible_state": visible_state,
        "human_action": {
            "action": action.value,
            "amount": amount,
        },
        "legal_actions": [
            {
                "action": legal.type.value,
                "min_amount": legal.min_amount,
                "max_amount": legal.max_amount,
            }
            for legal in legal_actions
        ],
        "required_json_schema": {
            "score": "integer 0-100",
            "label": "优秀|可接受|偏松|偏紧|风险过高",
            "reasoning": "short Chinese training feedback",
            "suggested_action": "fold|check|call|bet|raise|all_in|null",
            "suggested_amount": "integer|null",
        },
    }


def _codex_review_prompt(
    visible_state: Mapping[str, Any] | None,
    legal_actions: Sequence[LegalAction],
    action: ActionType,
    amount: int,
) -> str:
    payload = _human_review_prompt_payload(visible_state, legal_actions, action, amount)
    return (
        "你是德州扑克训练器的人类玩家复盘教练。"
        "请只根据 visible_state 中人类当时可见的信息评价 human_action。"
        "不要假设对手底牌。score 为 0 到 100。reasoning 用简短中文。"
        "如果有更推荐动作，suggested_action 必须来自 legal_actions；否则填 null。"
        "只返回 JSON，不要 Markdown。\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def _codex_decision_prompt(
    profile: BotProfile,
    visible_state: Mapping[str, Any] | None,
    legal_actions: Sequence[LegalAction],
) -> str:
    payload = {
        "profile": {
            "name": profile.name,
            "style": profile.style.value,
            "risk_tolerance": profile.risk_tolerance,
            "bluff_frequency": profile.bluff_frequency,
            "aggression": profile.aggression,
        },
        "visible_state": visible_state,
        "legal_actions": [
            {
                "action": action.type.value,
                "min_amount": action.min_amount,
                "max_amount": action.max_amount,
            }
            for action in legal_actions
        ],
    }
    return (
        "你是德州扑克训练器里的电脑玩家。只从 legal_actions 中选择一个后端合法动作。"
        "amount 必须在该动作的 min_amount 和 max_amount 范围内。"
        "reasoning 必须用简短中文解释牌局决策。只返回 JSON，不要 Markdown。\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def _parse_review_json(
    content: str,
    source: str,
    provider: str,
    model: str,
) -> HumanReviewResult:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} content is not strict JSON") from exc

    required_keys = {"score", "label", "reasoning", "suggested_action", "suggested_amount"}
    if not isinstance(parsed, dict) or set(parsed) != required_keys:
        raise ValueError(f"{source} JSON must contain exactly required keys")
    score = parsed["score"]
    label = parsed["label"]
    reasoning = parsed["reasoning"]
    suggested_action_value = parsed["suggested_action"]
    suggested_amount = parsed["suggested_amount"]
    if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
        raise ValueError(f"{source} score must be an integer between 0 and 100")
    if label not in {"优秀", "可接受", "偏松", "偏紧", "风险过高"}:
        raise ValueError(f"{source} label is not supported")
    if not isinstance(reasoning, str):
        raise ValueError(f"{source} reasoning must be a string")
    if suggested_action_value is None:
        suggested_action = None
    elif isinstance(suggested_action_value, str):
        try:
            suggested_action = ActionType(suggested_action_value)
        except ValueError as exc:
            raise ValueError(f"{source} suggested_action is not supported") from exc
    else:
        raise ValueError(f"{source} suggested_action must be a string or null")
    if suggested_amount is not None:
        if not isinstance(suggested_amount, int) or isinstance(suggested_amount, bool):
            raise ValueError(f"{source} suggested_amount must be an integer or null")
        if suggested_amount < 0:
            raise ValueError(f"{source} suggested_amount must be non-negative")
    return HumanReviewResult(
        score=score,
        label=label,
        reasoning=reasoning,
        suggested_action=suggested_action,
        suggested_amount=suggested_amount,
        provider=provider,
        model=model,
    )


def _parse_decision_json(content: str, source: str) -> DecisionResult:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} content is not strict JSON") from exc

    required_keys = {"action", "amount", "confidence", "reasoning"}
    if not isinstance(parsed, dict) or set(parsed) != required_keys:
        raise ValueError(f"{source} JSON must contain exactly required keys")

    action_value = parsed["action"]
    amount = parsed["amount"]
    confidence = parsed["confidence"]
    reasoning = parsed["reasoning"]
    if not isinstance(action_value, str):
        raise ValueError(f"{source} action must be a string")
    try:
        action = ActionType(action_value)
    except ValueError as exc:
        raise ValueError(f"{source} action is not supported") from exc
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValueError(f"{source} amount must be an integer")
    if (
        not isinstance(confidence, int | float)
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        raise ValueError(f"{source} confidence must be a number between 0 and 1")
    if not isinstance(reasoning, str):
        raise ValueError(f"{source} reasoning must be a string")
    return DecisionResult(
        action=action,
        amount=amount,
        confidence=float(confidence),
        reasoning=reasoning,
    )


def _raise_if_turn_failed(turn: Any) -> None:
    if not isinstance(turn, dict) or turn.get("status") != "failed":
        return
    error = turn.get("error")
    raise ValueError(f"Codex app-server turn failed: {error}")


def _should_buffer_json_parse_failure(value: str, exc: json.JSONDecodeError) -> bool:
    if not value.startswith(("{", "[")):
        return False
    return exc.msg in {
        "Unterminated string starting at",
        "Expecting value",
        "Expecting property name enclosed in double quotes",
        "Expecting ',' delimiter",
    } or exc.pos >= max(0, len(value) - 2)


def _preview_line(value: str, max_length: int = 500) -> str:
    compact = value.replace("\n", "\\n")
    if len(compact) <= max_length:
        return compact
    return f"{compact[:max_length - 3]}..."


def _extract_final_message(turn: Any) -> str | None:
    if not isinstance(turn, dict):
        return None
    items = turn.get("items")
    if not isinstance(items, list):
        return None
    agent_messages = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("type") == "agentMessage"
        and isinstance(item.get("text"), str)
    ]
    for item in reversed(agent_messages):
        if item.get("phase") == "final_answer":
            return item["text"]
    if agent_messages:
        return agent_messages[-1]["text"]
    return None


def _scaled_amount(action: LegalAction, aggression: float) -> int:
    span = action.max_amount - action.min_amount
    if span <= 0:
        return action.min_amount
    scale = min(0.35, max(0.0, aggression - 0.5))
    return min(action.max_amount, action.min_amount + int(span * scale))


def _first_legal_decision(
    legal_by_type: dict[ActionType, LegalAction],
    reasoning: str,
) -> DecisionResult:
    action = next(iter(legal_by_type.values()))
    return DecisionResult(
        action=action.type,
        amount=action.min_amount,
        confidence=0.4,
        reasoning=reasoning,
    )


def _hand_strength(cards: Sequence[Card]) -> float:
    if len(cards) >= 5:
        rank = evaluate_best(cards)
        category_scores = {
            HandCategory.HIGH_CARD: 0.26,
            HandCategory.PAIR: 0.48,
            HandCategory.TWO_PAIR: 0.67,
            HandCategory.THREE_OF_A_KIND: 0.76,
            HandCategory.STRAIGHT: 0.84,
            HandCategory.FLUSH: 0.88,
            HandCategory.FULL_HOUSE: 0.94,
            HandCategory.FOUR_OF_A_KIND: 0.98,
            HandCategory.STRAIGHT_FLUSH: 1.0,
        }
        kicker_bonus = min(0.07, sum(rank.tiebreakers[:2]) / 400)
        return min(1.0, category_scores[rank.category] + kicker_bonus)

    if len(cards) < 2:
        return 0.0

    first, second = cards[0], cards[1]
    high_rank = max(int(first.rank), int(second.rank))
    low_rank = min(int(first.rank), int(second.rank))
    suited_bonus = 0.05 if first.suit is second.suit else 0.0
    connected_bonus = 0.04 if high_rank - low_rank <= 1 else 0.0

    if high_rank == low_rank:
        return min(0.9, 0.48 + high_rank / 35)
    broadway_bonus = 0.08 if low_rank >= 10 else 0.0
    ace_bonus = 0.08 if high_rank == 14 else 0.0
    return min(
        0.82,
        0.18 + high_rank / 35 + low_rank / 70 + suited_bonus + connected_bonus
        + broadway_bonus + ace_bonus,
    )
