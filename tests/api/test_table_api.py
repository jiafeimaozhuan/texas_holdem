import json

import pytest
from fastapi.testclient import TestClient

from texas_holdem_trainer.ai.providers import HeuristicProvider
from texas_holdem_trainer.ai.service import AIService
from texas_holdem_trainer.api.schemas import CreateTableRequest, SubmitActionRequest
from texas_holdem_trainer.api.app import app, table_manager


@pytest.fixture(autouse=True)
def reset_table_manager() -> None:
    table_manager.reset()
    heuristic = HeuristicProvider()
    table_manager.ai_service = AIService(
        primary_provider=heuristic,
        fallback_provider=heuristic,
    )
    table_manager.bot_provider_templates = {}


def test_table_rest_flow_hides_bot_cards_and_records_ai_reasoning() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/table",
        json={
            "player_names": ["Hero", "Ada", "Babbage", "Claude"],
            "bot_styles": ["tight_aggressive", "conservative", "gto_leaning"],
            "starting_stack": 500,
            "small_blind": 5,
            "big_blind": 10,
            "human_seat": 0,
            "seed": 101,
        },
    )
    assert create_response.status_code == 201
    table_id = create_response.json()["table_id"]
    assert table_id

    hand_response = client.post(f"/api/table/{table_id}/hand")
    assert hand_response.status_code == 200
    started = hand_response.json()
    assert started["table_id"] == table_id
    assert started["state"]["hand_number"] == 1

    state_response = client.get(f"/api/table/{table_id}")
    assert state_response.status_code == 200
    state = state_response.json()
    assert state["ai_provider_status"] == "heuristic/local"
    assert state["street"] in {"preflop", "flop", "turn", "river", "complete"}
    assert state["players"][0]["hole_cards"]
    assert all("hole_cards" not in player for player in state["players"][1:])
    assert state["current_actor_seat"] in {0, None}

    private_bot_cards = [
        _card_code(card)
        for player in table_manager.tables[table_id].state.players[1:]
        for card in player.hole_cards
    ]
    serialized_state = state_response.text
    assert private_bot_cards
    assert all(card not in serialized_state for card in private_bot_cards)

    illegal_response = client.post(
        f"/api/table/{table_id}/action",
        json={"action": "raise", "amount": 1},
    )
    assert illegal_response.status_code == 400
    assert "detail" in illegal_response.json()

    final_state = state
    human_review_events = []
    if state["street"] != "complete":
        legal_action = _choose_legal_action(state["legal_actions"])
        action_response = client.post(
            f"/api/table/{table_id}/action",
            json=legal_action,
        )
        assert action_response.status_code == 200
        advanced = action_response.json()
        assert advanced["street"] in {"preflop", "flop", "turn", "river", "complete"}
        human_review_events = advanced["human_review_events"]
        assert human_review_events
        latest_review = human_review_events[-1]
        assert latest_review["type"] == "human_review"
        assert latest_review["seat"] == 0
        assert latest_review["action"] == legal_action["action"]
        assert latest_review["score"] >= 0
        assert latest_review["score"] <= 100
        assert latest_review["label"] in {
            "优秀",
            "可接受",
            "偏松",
            "偏紧",
            "风险过高",
        }
        assert latest_review["reasoning"]
        assert latest_review["provider"] == "heuristic"
        assert latest_review["model"] == "local"
        settled_response = client.get(f"/api/table/{table_id}")
        assert settled_response.status_code == 200
        final_state = settled_response.json()

    coach_events = final_state["coach_events"]
    assert coach_events
    assert all(event["provider"] == "heuristic" for event in coach_events)
    assert all(event["model"] == "local" for event in coach_events)

    history_response = client.get(f"/api/table/{table_id}/history")
    assert history_response.status_code == 200
    history = history_response.json()
    ai_events = [event for event in history["events"] if event["type"] == "ai_decision"]
    review_events = [
        event for event in history["events"] if event["type"] == "human_review"
    ]
    assert ai_events
    if human_review_events:
        assert review_events
        assert review_events[-1]["score"] == human_review_events[-1]["score"]
        assert review_events[-1]["reasoning"]
    assert all(event["provider"] == "heuristic" for event in ai_events)
    assert all(event["model"] == "local" for event in ai_events)
    assert all(event["reasoning"] for event in ai_events)
    assert all(event["source_reasoning"] for event in ai_events)
    assert all("hole_cards" not in json.dumps(event) for event in ai_events)


def test_unknown_table_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/api/table/does-not-exist")

    assert response.status_code == 404
    assert response.json()["detail"] == "table not found"


def test_human_fold_continues_hand_with_remaining_bots() -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/table",
        json={
            "player_names": ["Ada", "Babbage", "Claude", "Hero"],
            "bot_styles": ["tight_aggressive", "conservative", "gto_leaning"],
            "starting_stack": 500,
            "small_blind": 5,
            "big_blind": 10,
            "human_seat": 3,
            "seed": 101,
        },
    )
    assert create_response.status_code == 201
    table_id = create_response.json()["table_id"]

    hand_response = client.post(f"/api/table/{table_id}/hand")
    assert hand_response.status_code == 200
    started = hand_response.json()["state"]
    assert started["current_actor_seat"] == 3
    assert "fold" in {action["action"] for action in started["legal_actions"]}

    action_response = client.post(
        f"/api/table/{table_id}/action",
        json={"action": "fold", "amount": 0},
    )

    assert action_response.status_code == 200
    advanced = action_response.json()
    assert advanced["players"][3]["folded"] is True
    assert advanced["human_review_events"]
    assert advanced["human_review_events"][-1]["type"] == "human_review"
    assert advanced["human_review_events"][-1]["seat"] == 3
    assert advanced["human_review_events"][-1]["action"] == "fold"
    assert advanced["street"] == "preflop"
    assert advanced.get("current_actor_seat") != 3
    assert advanced["legal_actions"] == []

    settled_response = client.get(f"/api/table/{table_id}")
    assert settled_response.status_code == 200
    settled = settled_response.json()
    assert settled["street"] == "complete"
    assert settled.get("current_actor_seat") is None
    assert settled["legal_actions"] == []

    history_response = client.get(f"/api/table/{table_id}/history")
    assert history_response.status_code == 200
    history = history_response.json()
    human_fold_index = next(
        index
        for index, event in enumerate(history["events"])
        if event["type"] == "action"
        and event["seat"] == 3
        and event["action"] == "fold"
    )
    assert any(
        event["type"] == "ai_decision" for event in history["events"][human_fold_index + 1 :]
    )


@pytest.mark.asyncio
async def test_human_fold_broadcasts_ai_continuation_before_completion() -> None:
    state = table_manager.create_table(
        CreateTableRequest(
            player_names=["Ada", "Babbage", "Claude", "Hero"],
            bot_styles=["tight_aggressive", "conservative", "gto_leaning"],
            starting_stack=500,
            small_blind=5,
            big_blind=10,
            human_seat=3,
            seed=101,
        )
    )
    await table_manager.start_hand(state.table_id)
    queue = await table_manager.subscribe(state.table_id)
    await queue.get()

    await table_manager.submit_human_action(
        state.table_id,
        SubmitActionRequest(action="fold", amount=0),
    )

    updates = []
    while not queue.empty():
        updates.append(queue.get_nowait())

    assert any(
        update.players[3].folded
        and update.street != "complete"
        and update.current_actor_seat != 3
        for update in updates
    )
    assert updates[-1].street == "complete"


def _choose_legal_action(legal_actions: list[dict]) -> dict:
    preferred = ["check", "call", "bet", "raise", "all_in", "fold"]
    by_action = {action["action"]: action for action in legal_actions}
    for action_name in preferred:
        if action_name in by_action:
            action = by_action[action_name]
            amount = action["min_amount"]
            return {"action": action["action"], "amount": amount}
    raise AssertionError("expected at least one legal action")


def _card_code(card) -> str:
    rank_names = {
        2: "2",
        3: "3",
        4: "4",
        5: "5",
        6: "6",
        7: "7",
        8: "8",
        9: "9",
        10: "T",
        11: "J",
        12: "Q",
        13: "K",
        14: "A",
    }
    return f"{rank_names[int(card.rank)]}{card.suit.value}"
