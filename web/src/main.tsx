import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { primeRendersTokenMap } from "./canvas/registry";
import "./index.css";

// Prime the OIP renders-token map (#309) in the background: producer node
// types with no exact renderer resolve through their declared token once
// the server's /api/node-types payload arrives. Failure-tolerant; the
// canvas renders with exact-key resolution until (and unless) it lands.
void primeRendersTokenMap();

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
