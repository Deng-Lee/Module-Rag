import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    api
      .overview()
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <section>
      <h1>系统总览</h1>
      {err && <div className="error">{err}</div>}
      <div className="grid">
        <div className="card">
          <h2>资产统计</h2>
          <pre className="json">{JSON.stringify(data?.assets || {}, null, 2)}</pre>
        </div>
        <div className="card">
          <h2>健康概览</h2>
          <pre className="json">{JSON.stringify(data?.health || {}, null, 2)}</pre>
        </div>
        <div className="card">
          <h2>Provider 快照</h2>
          <pre className="json">{JSON.stringify(data?.providers || {}, null, 2)}</pre>
        </div>
      </div>
    </section>
  );
}
