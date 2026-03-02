import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function QueryTrace() {
  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);

  useEffect(() => {
    api.traces("?trace_type=query&limit=20").then((res) => setItems(res.items || []));
  }, []);

  const load = async (traceId: string) => {
    const res = await api.trace(traceId);
    setSelected(res);
  };

  return (
    <section>
      <h1>Query Trace</h1>
      <div className="grid">
        <div className="card">
          <h2>历史列表</h2>
          <ul className="list">
            {items.map((t) => (
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
          <pre className="json">{JSON.stringify(selected, null, 2)}</pre>
        </div>
      </div>
    </section>
  );
}
