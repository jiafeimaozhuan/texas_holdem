from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from texas_holdem_trainer.api.schemas import (
    CreateTableRequest,
    HistoryResponse,
    StartHandResponse,
    SubmitActionRequest,
    TableStateResponse,
    UpdateBotsRequest,
)
from texas_holdem_trainer.runtime.table_manager import (
    IllegalActionError,
    TableManager,
    TableNotFoundError,
)
from texas_holdem_trainer.runtime.config import build_default_table_manager


table_manager = build_default_table_manager()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await table_manager.close()


app = FastAPI(title="Texas Hold'em Trainer", lifespan=lifespan)


@app.post(
    "/api/table",
    response_model=TableStateResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_table(request: CreateTableRequest) -> TableStateResponse:
    try:
        return table_manager.create_table(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/table/{table_id}/hand",
    response_model=StartHandResponse,
    response_model_exclude_none=True,
)
async def start_hand(table_id: str) -> StartHandResponse:
    try:
        state = await table_manager.start_hand(table_id)
    except TableNotFoundError as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartHandResponse(table_id=table_id, state=state)


@app.get(
    "/api/table/{table_id}",
    response_model=TableStateResponse,
    response_model_exclude_none=True,
)
def get_table(table_id: str) -> TableStateResponse:
    try:
        return table_manager.get_state(table_id)
    except TableNotFoundError as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc


@app.post(
    "/api/table/{table_id}/action",
    response_model=TableStateResponse,
    response_model_exclude_none=True,
)
async def submit_action(
    table_id: str,
    request: SubmitActionRequest,
    background_tasks: BackgroundTasks,
) -> TableStateResponse:
    try:
        state = await table_manager.submit_human_action(
            table_id,
            request,
            advance_ai=False,
        )
        background_tasks.add_task(table_manager.advance_ai_turns, table_id)
        return state
    except TableNotFoundError as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc
    except IllegalActionError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/table/{table_id}/history",
    response_model=HistoryResponse,
    response_model_exclude_none=True,
)
def get_history(table_id: str) -> HistoryResponse:
    try:
        return table_manager.get_history(table_id)
    except TableNotFoundError as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc


@app.put(
    "/api/table/{table_id}/bots",
    response_model=TableStateResponse,
    response_model_exclude_none=True,
)
async def update_bots(
    table_id: str,
    request: UpdateBotsRequest,
) -> TableStateResponse:
    try:
        state = table_manager.update_bots(table_id, request)
        await table_manager.broadcast(table_id, state)
        return state
    except TableNotFoundError as exc:
        raise HTTPException(status_code=404, detail="table not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.websocket("/ws/table/{table_id}")
async def table_socket(websocket: WebSocket, table_id: str) -> None:
    await websocket.accept()
    try:
        queue = await table_manager.subscribe(table_id)
    except TableNotFoundError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        while True:
            state = await queue.get()
            await websocket.send_json(state.model_dump(mode="json", exclude_none=True))
    except WebSocketDisconnect:
        pass
    finally:
        table_manager.unsubscribe(table_id, queue)
