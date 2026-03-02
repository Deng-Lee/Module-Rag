import { NavLink, Route, Routes } from "react-router-dom";
import Overview from "./routes/Overview";
import Browser from "./routes/Browser";
import Ingestion from "./routes/Ingestion";
import IngestionTrace from "./routes/IngestionTrace";
import QueryTrace from "./routes/QueryTrace";
import EvalPanel from "./routes/EvalPanel";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">MODULE-RAG</div>
        <nav className="nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/browser">Browser</NavLink>
          <NavLink to="/ingestion">Ingestion</NavLink>
          <NavLink to="/ingestion-trace">Ingestion Trace</NavLink>
          <NavLink to="/query-trace">Query Trace</NavLink>
          <NavLink to="/eval">Eval</NavLink>
        </nav>
      </header>

      <main className="container">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/browser" element={<Browser />} />
          <Route path="/ingestion" element={<Ingestion />} />
          <Route path="/ingestion-trace" element={<IngestionTrace />} />
          <Route path="/query-trace" element={<QueryTrace />} />
          <Route path="/eval" element={<EvalPanel />} />
        </Routes>
      </main>
    </div>
  );
}
