import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

const bootstrap = window.__DFS_AGGREGATE_BOOTSTRAP__ || {};

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App bootstrap={bootstrap} />
  </React.StrictMode>,
);
