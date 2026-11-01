import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Landing from "./landing/Landing.jsx";
import { applyTheme, initialTheme } from "./theme.js";
import "./styles.css";
import "./hud.css";

applyTheme(initialTheme());   // before the first paint, so the dashboard never flashes the wrong theme

// "/" is the landing page, "#/app" the dashboard
const isApp = () => window.location.hash.startsWith("#/app");

function Root() {
  const [app, setApp] = useState(isApp);
  useEffect(() => {
    const on = () => { setApp(isApp()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("lp-root", !app);
    if (app) document.title = "Kairo";
  }, [app]);
  return app ? <App /> : <Landing />;
}

createRoot(document.getElementById("root")).render(<Root />);
