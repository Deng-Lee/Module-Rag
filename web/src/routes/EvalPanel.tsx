import { useEffect, useState } from "react";
import { api } from "../api/client";

export default function EvalPanel() {
  const [runs, setRuns] = useState<any[]>([]);

  useEffect(() => {
    api.evalRuns().then((res) => setRuns(res.items || []));
  }, []);

  return (
    <section>
      <h1>评估面板</h1>
      <div className="card">
        <h2>历史评估</h2>
        <pre className="json">{JSON.stringify(runs, null, 2)}</pre>
      </div>
    </section>
  );
}
