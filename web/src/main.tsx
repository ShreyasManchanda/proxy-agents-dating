import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api";
import { Handshake } from "@phosphor-icons/react";
import "./styles.css";
import Landing from "./pages/Landing";
import Pool from "./pages/Pool";
import Profile from "./pages/Profile";
import DateView from "./pages/DateView";

/** /demo is a fixed public address for the saved, frozen 25-person pool. It reads only the database. */
function Demo() {
  const [token, setToken] = useState<string | null | undefined>(undefined);
  useEffect(() => { api.config().then((c) => setToken(c.demo_token ?? null)).catch(() => setToken(null)); }, []);
  if (token === undefined) return <p className="muted">Opening the demo…</p>;
  if (token === null) return <div className="empty"><h3>The demo is not available right now</h3><Link to="/">Back to start</Link></div>;
  return <Navigate to={`/p/${token}`} replace />;
}

/** /pool/<token> is accepted as an alias of /p/<token>. */
function PoolAlias() {
  const { token = "" } = useParams();
  return <Navigate to={`/p/${token}`} replace />;
}

function Shell() {
  return (
    <>
      <header className="bar">
        <div className="bar-in">
          <Link to="/" className="brand"><Handshake size={22} weight="duotone" aria-hidden /> Proxy</Link>
          <nav aria-label="Primary">
            <Link to="/">New run</Link>
            <Link to="/demo">Demo</Link>
            <a href="#about-data">What agents see</a>
          </nav>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/pool/:token" element={<PoolAlias />} />
          <Route path="/p/:token" element={<Pool />} />
          <Route path="/p/:token/person/:id" element={<Profile />} />
          <Route path="/p/:token/date/:id" element={<DateView />} />
          <Route path="*" element={<div className="empty"><h3>Page not found</h3><Link to="/">Back to start</Link></div>} />
        </Routes>
      </main>
      <footer className="site" id="about-data">
        Agents only read the public LinkedIn and Instagram that are entered. We rank compatibility, not eligibility.
        Profiles are processed by third-party AI providers (Google Gemini, Groq). Consistency of the results is measurable; correctness is not.
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter><Shell /></BrowserRouter>
  </React.StrictMode>,
);
