import { useEffect, useState } from "react";
import { api } from "../api/client";

type StageRow = {
  name: string;
  start_ts: string | number;
  end_ts: string | number;
  duration_ms: number;
};

export default function IngestionTrace() {
  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [keyword, setKeyword] = useState("");
  const [offset, setOffset] = useState(0);
  const [limit] = useState(10);
  const [err, setErr] = useState("");

  const loadList = async () => {
    try {
      setErr("");
      const params = new URLSearchParams();
      params.set("trace_type", "ingestion");
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      const res = await api.traces(`?${params.toString()}`);
      setItems(res.items || []);
    } catch (e) {
      setErr(String(e));
      setItems([]);
    }
  };

  useEffect(() => {
    loadList();
  }, [offset, limit]);

  const load = async (traceId: string) => {
    try {
      const res = await api.trace(traceId);
      setSelected(res);
    } catch (e) {
      setErr(String(e));
      setSelected(null);
    }
  };

  const shown = items.filter((t) => {
    if (!keyword.trim()) return true;
    const k = keyword.trim().toLowerCase();
    return String(t.trace_id || "").toLowerCase().includes(k) || String(t.status || "").toLowerCase().includes(k);
  });

  const traceObj = selected?.trace || selected || {};
  const spans = Array.isArray(traceObj.spans) ? traceObj.spans : [];
  const stageRows: StageRow[] = spans.map((s: any) => {
    const start = Number(s.start_ts || 0);
    const end = Number(s.end_ts || 0);
    const durationMs = start > 0 && end > 0 && end >= start ? Math.round((end - start) * 1000) : 0;
    return {
      name: String(s.name || "-"),
      start_ts: s.start_ts || "-",
      end_ts: s.end_ts || "-",
      duration_ms: durationMs,
    };
  });

  return (
    <section>
      <h1>Ingestion Trace</h1>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <input
          className="input"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="关键词（trace_id / status）"
        />
        <button className="btn" type="button" disabled={offset <= 0} onClick={() => setOffset((prev) => Math.max(0, prev - limit))}>
          上一页
        </button>
        <button className="btn" type="button" onClick={() => setOffset((prev) => prev + limit)}>
          下一页
        </button>
        <span className="muted">
          offset={offset} limit={limit}
        </span>
      </div>
      <div className="grid">
        <div className="card">
          <h2>历史列表</h2>
          <ul className="list">
            {shown.map((t) => (
              <li key={t.trace_id}>
                <button className="link" onClick={() => load(t.trace_id)}>
                  {t.trace_id}
                </button>
                <span className="muted"> {t.status}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h2>Trace 详情</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Stage</th>
                <th>start_ts</th>
                <th>end_ts</th>
                <th>耗时(ms)</th>
              </tr>
            </thead>
            <tbody>
              {stageRows.map((s: StageRow) => (
                <tr key={`${s.name}-${s.start_ts}`}>
                  <td>{s.name}</td>
                  <td>{String(s.start_ts)}</td>
                  <td>{String(s.end_ts)}</td>
                  <td>{s.duration_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <pre className="json">{JSON.stringify(selected, null, 2)}</pre>
        </div>
      </div>
    </section>
  );
}
