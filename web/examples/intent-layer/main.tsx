import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { IntentOverlay } from "../../src/intent-overlay";
import { captureTab, type Screenshot } from "./capture";
import { useFormHost } from "./formHost";
import { createFormTransport, type Evidence, type FormState } from "./transport";
import "./style.css";

function FormExample() {
  const surface = useRef<HTMLElement>(null);
  const evidence = useRef<Evidence>({ targets: [] });
  const [state, setState] = useState<FormState>({ fields: { email: "", max_flow: 0 }, revision: 0 });
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState("Connecting to the local form host...");
  const [screenshot, setScreenshot] = useState<Screenshot>();
  const [capturing, setCapturing] = useState(false);
  const transport = useMemo(() => createFormTransport(setState, () => evidence.current), []);
  const { host, targets } = useFormHost(surface, state, transport.thread);
  evidence.current = { targets, ...(screenshot ? { screenshot } : {}) };
  useEffect(() => {
    let cancelled = false;
    void transport.state().then(() => {
      if (!cancelled) { setReady(true); setStatus("Ready. Capture is optional; IDs and geometry always travel with a remark."); }
    }).catch((error: Error) => { if (!cancelled) setStatus(error.message + " Start the form backend on port 8003."); });
    return () => { cancelled = true; };
  }, [transport]);

  const capture = async () => {
    if (!surface.current) return;
    setScreenshot(undefined);
    setCapturing(true);
    setStatus("Choose this browser tab in the capture picker.");
    const elements = Array.from(surface.current.querySelectorAll<HTMLElement>("[data-intent-id]"));
    const rects = elements.map((element) => element.getBoundingClientRect());
    const left = Math.min(...rects.map((rect) => rect.left)), top = Math.min(...rects.map((rect) => rect.top));
    const right = Math.max(...rects.map((rect) => rect.right)), bottom = Math.max(...rects.map((rect) => rect.bottom));
    const result = await captureTab({ x: left, y: top, width: right - left, height: bottom - top },
      elements.map((element) => element.dataset.intentId!));
    setCapturing(false);
    if (result.status === "attached") {
      setScreenshot(result.screenshot);
      setStatus("Real browser-tab PNG attached to the next remark. Capture sharing has stopped.");
    } else setStatus(result.message);
  };
  const reply = async () => {
    try { await transport.demoReply(); setStatus("The fixed demo agent posted a question and a typed field proposal."); }
    catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
  };
  return <main className="example">
    <header>
      <p className="eyebrow">Independent intent layer example</p>
      <h1>Review a plain form</h1>
      <p>Draw across a field, double-click nearby to write, then send the remark.
        A fixed demo reply lets you answer, inspect a preview, approve, and put the exact values back.</p>
      <div className="actions">
        <button disabled={!ready} onClick={() => setActive(!active)}>{active ? "Put pen down" : "Mark up fields"}</button>
        <button disabled={!ready || capturing} onClick={() => void capture()}>Capture field crop</button>
        <button disabled={!ready} onClick={() => void reply()}>Demo reply to sent remarks</button>
      </div>
      <p role="status">{status}</p>
      <p className="disclosure">Local, in-memory prototype. Demo replies are fixed fixtures, with no AI provider.
        Field patches run in the form backend; the overlay only draws previews.</p>
    </header>
    <section ref={surface} className="surface" aria-label="Form review surface">
      <div className="fields">
        <label data-intent-id="email" data-intent-label="Email" className="field">
          <span>Email</span><input aria-label="Email" value={state.fields.email} readOnly />
        </label>
        <label data-intent-id="max_flow" data-intent-label="Maximum flow" className="field">
          <span>Maximum flow</span><input aria-label="Maximum flow" value={state.fields.max_flow} readOnly />
        </label>
        <p className="revision">Host revision: <output data-testid="form-revision">{state.revision}</output></p>
      </div>
      {/* One overlay lifetime per mounted form; active toggles retain its ink. */}
      {ready ? <IntentOverlay active={active} host={host} onExit={() => setActive(false)}
        onFiled={() => { setScreenshot(undefined); setStatus("Remark sent. Request the fixed demo reply to inspect the host patch."); }} /> : null}
    </section>
    <details className="evidence"><summary>Attached evidence and target metadata</summary>
      <p>{screenshot ? "Actual browser pixels, cropped from a tab media frame." : "No screenshot attached. Requests still include stable IDs and measured DOM boxes."}</p>
      {screenshot ? <img alt="Actual browser field crop" src={screenshot.dataUrl} /> : null}
      <pre>{JSON.stringify(targets, null, 2)}</pre>
    </details>
  </main>;
}
createRoot(document.getElementById("root")!).render(<FormExample />);
