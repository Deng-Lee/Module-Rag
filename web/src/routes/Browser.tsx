import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function Browser() {
  const [docs, setDocs] = useState<any[]>([]);
  const [docFilter, setDocFilter] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(10);
  const [chunkId, setChunkId] = useState("");
  const [chunk, setChunk] = useState<any>(null);
  const [err, setErr] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      setErr("");
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      params.set("include_deleted", includeDeleted ? "true" : "false");
      if (docFilter.trim()) {
        params.set("doc_id", docFilter.trim());
      }
      const res = await api.documents(`?${params.toString()}`);
      setDocs(res.items || []);
    } catch (e) {
      setErr(String(e));
      setDocs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [offset, includeDeleted, limit]);

  const applyFilter = () => {
    setOffset(0);
    loadDocuments();
  };

  const loadChunk = async () => {
    if (!chunkId.trim()) return;
    try {
      setErr("");
      const res = await api.chunk(chunkId.trim());
      setChunk(res);
    } catch (e) {
      setErr(String(e));
      setChunk(null);
    }
  };

  return (
    <section>
      <h1>数据浏览器</h1>
      {err && <div className="error">{err}</div>}
      <div className="card">
        <h2>文档版本</h2>
        <div className="row">
          <input
            className="input"
            value={docFilter}
            onChange={(e) => setDocFilter(e.target.value)}
            placeholder="doc_id"
          />
          <label className="muted">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => {
                setOffset(0);
                setIncludeDeleted(e.target.checked);
              }}
            />
            include_deleted
          </label>
          <button className="btn" onClick={applyFilter} type="button">
            过滤
          </button>
          <button
            className="btn"
            type="button"
            disabled={offset <= 0 || loading}
            onClick={() => setOffset((prev) => Math.max(0, prev - limit))}
          >
            上一页
          </button>
          <button
            className="btn"
            type="button"
            disabled={loading || docs.length < limit}
            onClick={() => setOffset((prev) => prev + limit)}
          >
            下一页
          </button>
          <span className="muted">
            offset={offset} limit={limit}
          </span>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>doc_id</th>
              <th>version_id</th>
              <th>status</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr
                key={`${d.doc_id}-${d.version_id}`}
                onClick={() => {
                  if (d.chunk_id) {
                    setChunkId(String(d.chunk_id));
                  }
                }}
              >
                <td>{d.doc_id}</td>
                <td>{d.version_id}</td>
                <td>{d.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Chunk 详情</h2>
        <div className="row">
          <input
            className="input"
            value={chunkId}
            onChange={(e) => setChunkId(e.target.value)}
            placeholder="chunk_id"
          />
          <button className="btn" onClick={loadChunk}>
            拉取
          </button>
        </div>
        {chunk && (
          <div className="row">
            <span className="muted">doc_id: {chunk.doc_id || "-"}</span>
            <span className="muted">version_id: {chunk.version_id || "-"}</span>
            <span className="muted">section_path: {chunk.section_path || "-"}</span>
            <span className="muted">page_range: {chunk.page_range || "-"}</span>
            <span className="muted">chunk_text: {String(chunk.chunk_text || "").slice(0, 80) || "-"}</span>
          </div>
        )}
        <pre className="json">{JSON.stringify(chunk, null, 2)}</pre>
      </div>
    </section>
  );
}
