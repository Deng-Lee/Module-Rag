import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function QueryTrace() {
  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [queryResult, setQueryResult] = useState<any>(null);
  const [keyword, setKeyword] = useState("");
  const [offset, setOffset] = useState(0);
  const [limit] = useState(10);
  const [err, setErr] = useState("");

  const loadList = async () => {
    try {
      setErr("");
      const params = new URLSearchParams();
      params.set("trace_type", "query");
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

  const runQuery = async () => {
    if (!query.trim()) {
      setErr("请输入查询内容");
      return;
    }
    try {
      setErr("");
      const res = await api.query({ query: query.trim(), top_k: topK, strategy_config_id: "default" });
      setQueryResult(res);
      await loadList();
    } catch (e) {
      setErr(String(e));
      setQueryResult(null);
    }
  };

  const shown = items.filter((t) => {
    if (!keyword.trim()) return true;
    const k = keyword.trim().toLowerCase();
    return String(t.trace_id || "").toLowerCase().includes(k) || String(t.status || "").toLowerCase().includes(k);
  });

  const traceObj = selected?.trace || selected || {};
  const spans = Array.isArray(traceObj.spans) ? traceObj.spans : [];
  const evidenceKinds = new Set<string>();
  spans.forEach((s: any) => {
    (s.events || []).forEach((e: any) => {
      const kind = String(e.kind || "");
      if (kind.includes("retrieval") || kind.includes("fusion") || kind.includes("rerank")) {
        evidenceKinds.add(kind);
      }
    });
  });
  const evidence = Array.from(evidenceKinds);

  return (
    <section>
      <h1>Query Trace</h1>
      {err && <div className="error">{err}</div>}
      <div className="card">
        <h2>执行查询</h2>
        <div className="row">
          <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="query" />
          <input
            className="input"
            value={String(topK)}
            onChange={(e) => setTopK(Number(e.target.value || 5))}
            placeholder="top_k"
          />
          <button className="btn" type="button" onClick={runQuery}>
            执行查询
          </button>
        </div>
        {queryResult?.status === "ok" && Array.isArray(queryResult?.sources) && queryResult.sources.length === 0 && (
          <div className="muted">无命中</div>
        )}
        <pre className="json">{JSON.stringify(queryResult, null, 2)}</pre>
      </div>

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
          <h3>检索证据</h3>
          <div className="row">
            <span className="muted">retrieval / fusion / rerank</span>
          </div>
          {evidence.length > 0 ? (
            <ul className="list">
              {evidence.map((k) => (
                <li key={k}>{k}</li>
              ))}
            </ul>
          ) : (
            <div className="muted">暂无检索证据</div>
          )}
          <pre className="json">{JSON.stringify(selected, null, 2)}</pre>
        </div>
      </div>
    </section>
  );
}
