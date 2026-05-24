import type {
  CreateTableRequest,
  HistoryEventView,
  StartHandResponse,
  SubmitActionRequest,
  TableStateResponse,
  UpdateBotsRequest,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL?.replace(/\/$/, "");

export interface HistoryResponse {
  table_id: string;
  events: HistoryEventView[];
}

function getWebSocketBaseUrl(): string {
  if (WS_BASE_URL) {
    return WS_BASE_URL;
  }

  if (API_BASE_URL) {
    return API_BASE_URL.replace(/^http/, "ws");
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
}

async function requestJson<TResponse>(
  path: string,
  init?: RequestInit,
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `API request failed: ${response.status} ${response.statusText}${body ? ` - ${body}` : ""}`,
    );
  }

  return response.json() as Promise<TResponse>;
}

export async function createTable(
  request: CreateTableRequest,
): Promise<TableStateResponse> {
  return requestJson<TableStateResponse>("/api/table", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getTable(tableId: string): Promise<TableStateResponse> {
  return requestJson<TableStateResponse>(`/api/table/${tableId}`);
}

export async function startHand(tableId: string): Promise<TableStateResponse> {
  const response = await requestJson<StartHandResponse>(`/api/table/${tableId}/hand`, {
    method: "POST",
  });
  return response.state;
}

export async function getHistory(tableId: string): Promise<HistoryResponse> {
  return requestJson<HistoryResponse>(`/api/table/${tableId}/history`);
}

export async function updateBots(
  tableId: string,
  request: UpdateBotsRequest,
): Promise<TableStateResponse> {
  return requestJson<TableStateResponse>(`/api/table/${tableId}/bots`, {
    method: "PUT",
    body: JSON.stringify(request),
  });
}

export async function submitAction(
  tableId: string,
  request: SubmitActionRequest,
): Promise<TableStateResponse> {
  return requestJson<TableStateResponse>(`/api/table/${tableId}/action`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function connectTableSocket(
  tableId: string,
  onState: (state: TableStateResponse) => void,
): WebSocket {
  const socketBase = getWebSocketBaseUrl();
  const socket = new WebSocket(`${socketBase}/ws/table/${tableId}`);

  socket.addEventListener("message", (event) => {
    onState(JSON.parse(event.data) as TableStateResponse);
  });

  return socket;
}
