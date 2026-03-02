import { useState } from "react";
import { api } from "../api/client";

export default function Ingestion() {
  const [filePath, setFilePath] = useState("");
  const [docId, setDocId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string>("");

  const submitIngest = async () => {
    try {
      const res = await api.ingest({ file_path: filePath, policy: "skip" });
      setResult(res);
    } catch (e) {
      setErr(String(e));
    }
  };

  const submitDelete = async () => {
    try {
      const res = await api.del({ doc_id: docId, version_id: versionId, mode: "soft" });
      setResult(res);
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <section>
      <h1>Ingestion 管理器</h1>
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
          <button className="btn" onClick={submitIngest}>
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
          <button className="btn" onClick={submitDelete}>
            Delete
          </button>
        </div>
      </div>

      <div className="card">
        <h2>结果</h2>
        <pre className="json">{JSON.stringify(result, null, 2)}</pre>
      </div>
    </section>
  );
}
