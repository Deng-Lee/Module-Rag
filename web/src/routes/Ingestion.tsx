import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function Ingestion() {
  const [filePath, setFilePath] = useState("");
  const [docId, setDocId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [validationErr, setValidationErr] = useState<string>("");
  const [err, setErr] = useState<string>("");

  const loadHistory = async () => {
    try {
      const res = await api.traces("?trace_type=ingestion&limit=10&offset=0");
      setHistory(res.items || []);
    } catch {
      setHistory([]);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const submitIngest = async () => {
    if (!filePath.trim()) {
      setValidationErr("请输入 file_path");
      return;
    }
    try {
      setValidationErr("");
      setErr("");
      const res = await api.ingest({ file_path: filePath.trim(), policy: "skip" });
      setResult(res);
      await loadHistory();
    } catch (e) {
      setErr(String(e));
    }
  };

  const submitDelete = async () => {
    try {
      setErr("");
      const res = await api.del({ doc_id: docId, version_id: versionId, mode: "soft" });
      setResult(res);
      await loadHistory();
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <section>
      <h1>Ingestion 管理器</h1>
      {validationErr && <div className="error">{validationErr}</div>}
      {err && <div className="error">{err}</div>}
      <div className="card">
        <h2>触发摄取</h2>
        <div className="row">
          <input
            className="input"
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
            placeholder="file_path"
          />
          <button className="btn" onClick={submitIngest} type="button">
            Ingest
          </button>
        </div>
      </div>
      <div className="card">
        <h2>删除文档</h2>
        <div className="row">
          <input
            className="input"
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            placeholder="doc_id"
          />
          <input
            className="input"
            value={versionId}
            onChange={(e) => setVersionId(e.target.value)}
            placeholder="version_id (optional)"
          />
          <button className="btn" onClick={submitDelete} type="button">
            Delete
          </button>
        </div>
      </div>

      <div className="card">
        <h2>结果</h2>
        {result?.trace_id && (
          <div className="row">
            <span className="muted">trace_id: {result.trace_id}</span>
            <span className="muted">doc_id: {result?.structured?.doc_id || "-"}</span>
            <span className="muted">version_id: {result?.structured?.version_id || "-"}</span>
            <Link to="/ingestion-trace">查看 Trace</Link>
          </div>
        )}
        <pre className="json">{JSON.stringify(result, null, 2)}</pre>
      </div>

      <div className="card">
        <h2>最近任务（历史任务）</h2>
        <ul className="list">
          {history.map((h) => (
            <li key={h.trace_id}>
              <span>{h.trace_id}</span>
              <span className="muted"> {h.status}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
