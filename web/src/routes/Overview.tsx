import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<string>("");

  const refresh = async () => {
    try {
      setLoading(true);
      setErr("");
      const res = await api.overview();
      setData(res);
      setLastRefreshAt(new Date().toLocaleTimeString());
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => {
      refresh();
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const providers = Object.entries(data?.providers || {}) as Array<[string, any]>;

  return (
    <section>
      <h1>系统总览</h1>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <button className="btn" onClick={refresh} disabled={loading}>
          {loading ? "刷新中..." : "刷新"}
        </button>
        <span className="muted">最后刷新: {lastRefreshAt || "-"}</span>
      </div>
      <div className="grid">
        <div className="card">
          <h2>资产统计</h2>
          <pre className="json">{JSON.stringify(data?.assets || {}, null, 2)}</pre>
        </div>
        <div className="card">
          <h2>健康概览</h2>
          <pre className="json">{JSON.stringify(data?.health || {}, null, 2)}</pre>
        </div>
      </div>

      <div className="card">
        <h2>Provider 快照</h2>
        {providers.length === 0 ? (
          <div className="muted">暂无 providers 快照</div>
        ) : (
          <div className="list">
            {providers.map(([name, detail]) => {
              const opened = expandedProvider === name;
              return (
                <div className="card" key={name}>
                  <div className="row">
                    <strong>{name}</strong>
                    <button
                      className="link"
                      onClick={() => setExpandedProvider(opened ? null : name)}
                      type="button"
                    >
                      {opened ? "收起详情" : "展开详情"}
                    </button>
                  </div>
                  {opened && <pre className="json">{JSON.stringify(detail || {}, null, 2)}</pre>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
