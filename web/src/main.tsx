import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Handshake } from "@phosphor-icons/react";
import "./styles.css";
import Landing from "./pages/Landing";
import Pool from "./pages/Pool";
import Profile from "./pages/Profile";
import DateView from "./pages/DateView";

function Shell() {
  return (
    <>
      <header className="bar">
        <div className="bar-in">
          <Link to="/" className="brand"><Handshake size={22} weight="duotone" aria-hidden /> Proxy</Link>
          <nav aria-label="Primary">
            <Link to="/">New run</Link>
            <a href="#about-data">What agents see</a>
          </nav>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
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
