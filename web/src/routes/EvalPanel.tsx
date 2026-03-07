import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function EvalPanel() {
  const [runs, setRuns] = useState<any[]>([]);
  const [runResult, setRunResult] = useState<any>(null);
  const [datasetId, setDatasetId] = useState("rag_eval_small");
  const [strategyConfigId, setStrategyConfigId] = useState("default");
  const [topK, setTopK] = useState(5);
  const [metric, setMetric] = useState("hit_rate@k");
  const [window, setWindow] = useState(30);
  const [trends, setTrends] = useState<any>({ metric: "hit_rate@k", window: 30, points: [] });
  const [err, setErr] = useState("");

  const loadRuns = async () => {
    try {
      const res = await api.evalRuns("?limit=20&offset=0");
      setRuns(res.items || []);
    } catch {
      setRuns([]);
    }
  };

  const loadTrends = async (m: string, w: number) => {
    try {
      const res = await api.evalTrends(m, w);
      setTrends(res);
    } catch (e) {
      setErr(String(e));
      setTrends({ metric: m, window: w, points: [] });
    }
  };

  useEffect(() => {
    loadRuns();
  }, []);

  useEffect(() => {
    loadTrends(metric, window);
  }, [metric, window]);

  const runEval = async () => {
    try {
      setErr("");
      const res = await api.evalRun({
        dataset_id: datasetId,
        strategy_config_id: strategyConfigId,
        top_k: topK,
      });
      setRunResult(res);
      await loadRuns();
      await loadTrends(metric, window);
    } catch (e) {
      setErr(String(e));
      setRunResult(null);
    }
  };

  return (
    <section>
      <h1>评估面板</h1>
      {err && <div className="error">{err}</div>}
      <div className="card">
        <h2>运行评估</h2>
        <div className="row">
          <input
            className="input"
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            placeholder="dataset_id"
          />
          <input
            className="input"
            value={strategyConfigId}
            onChange={(e) => setStrategyConfigId(e.target.value)}
            placeholder="strategy_config_id"
          />
          <input className="input" value={String(topK)} onChange={(e) => setTopK(Number(e.target.value || 5))} />
          <button className="btn" type="button" onClick={runEval}>
            Run Eval
          </button>
        </div>
        <pre className="json">{JSON.stringify(runResult, null, 2)}</pre>
      </div>

      <div className="card">
        <h2>历史评估</h2>
        <pre className="json">{JSON.stringify(runs, null, 2)}</pre>
      </div>

      <div className="card">
        <h2>趋势图</h2>
        <div className="row">
          <label className="muted">
            metric
            <select className="input" value={metric} onChange={(e) => setMetric(e.target.value)}>
              <option value="hit_rate@k">hit_rate@k</option>
              <option value="mrr">mrr</option>
              <option value="ndcg@k">ndcg@k</option>
            </select>
          </label>
          <label className="muted">
            window
            <select className="input" value={String(window)} onChange={(e) => setWindow(Number(e.target.value))}>
              <option value="7">7</option>
              <option value="30">30</option>
              <option value="90">90</option>
            </select>
          </label>
        </div>
        {Array.isArray(trends?.points) && trends.points.length === 0 ? (
          <div className="muted">无数据</div>
        ) : (
          <pre className="json">{JSON.stringify(trends, null, 2)}</pre>
        )}
      </div>
    </section>
  );
}
