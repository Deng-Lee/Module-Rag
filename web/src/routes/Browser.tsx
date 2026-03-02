import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function Browser() {
  const [docs, setDocs] = useState<any[]>([]);
  const [chunkId, setChunkId] = useState("");
  const [chunk, setChunk] = useState<any>(null);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    api
      .documents("?limit=20&offset=0")
      .then((res) => setDocs(res.items || []))
      .catch((e) => setErr(String(e)));
  }, []);

  const loadChunk = async () => {
    if (!chunkId) return;
    try {
      const res = await api.chunk(chunkId);
      setChunk(res);
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <section>
      <h1>数据浏览器</h1>
      {err && <div className="error">{err}</div>}
      <div className="card">
        <h2>文档版本</h2>
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
              <tr key={`${d.doc_id}-${d.version_id}`}>
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
        <pre className="json">{JSON.stringify(chunk, null, 2)}</pre>
      </div>
    </section>
  );
}
