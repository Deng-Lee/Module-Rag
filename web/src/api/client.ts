export const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  overview: () => http<{ assets: Record<string, number>; health: any; providers: any }>("/overview"),
  traces: (params = "") => http<{ items: any[]; limit: number; offset: number }>(`/traces${params}`),
  trace: (id: string) => http<any>(`/trace/${id}`),
  documents: (params = "") => http<{ items: any[] }>(`/documents${params}`),
  chunk: (id: string) => http<any>(`/chunk/${id}`),
  ingest: (payload: any) => http<any>("/ingest", { method: "POST", body: JSON.stringify(payload) }),
  del: (payload: any) => http<any>("/delete", { method: "POST", body: JSON.stringify(payload) }),
  evalRuns: () => http<{ items: any[] }>("/eval/runs"),
};
