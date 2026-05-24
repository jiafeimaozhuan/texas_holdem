import type {
  CreateTableRequest,
  StartHandResponse,
  SubmitActionRequest,
  TableStateResponse,
} from "../types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

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

export async function startHand(tableId: string): Promise<TableStateResponse> {
  const response = await requestJson<StartHandResponse>(`/api/table/${tableId}/hand`, {
    method: "POST",
  });
  return response.state;
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
  const socketBase = API_BASE_URL.replace(/^http/, "ws");
  const socket = new WebSocket(`${socketBase}/ws/table/${tableId}`);

  socket.addEventListener("message", (event) => {
    onState(JSON.parse(event.data) as TableStateResponse);
  });

  return socket;
}
