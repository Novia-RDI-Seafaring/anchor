/**
 * Text-layer selection constraint, ported from pdf.js's `TextLayerBuilder`.
 *
 * `PdfPageCanvas` renders a bare `pdfjs.TextLayer`, which produces selectable
 * spans but does NOT wire up selection *constraint*. Without it, dragging
 * across the gaps of a multi-column page (or the space between paragraphs)
 * leaks the selection into the other column, because the browser extends the
 * selection in DOM order and the columns are adjacent in the DOM.
 *
 * pdf.js fixes this with an `endOfContent` sink element that a global
 * `selectionchange` listener repositions next to the current selection anchor,
 * plus a `selecting` class on the active text layer (see pdf_viewer.css:
 * `.textLayer.selecting .endOfContent { inset: 0 … }`). This is a faithful,
 * self-contained port of that mechanism so we do not have to import the whole
 * `pdf_viewer.mjs` components bundle.
 *
 * Usage: after a text layer renders, call `registerTextLayerSelection(div)` and
 * invoke the returned disposer when the layer is torn down / re-rendered.
 */

const textLayers = new Map<HTMLElement, HTMLElement>();
let selectionAC: AbortController | null = null;
let isFirefox: boolean | undefined;

function reset(end: HTMLElement, textLayer: HTMLElement): void {
  textLayer.append(end);
  end.style.width = "";
  end.style.height = "";
  textLayer.classList.remove("selecting");
}

function enableGlobalSelectionListener(): void {
  if (selectionAC) return;
  selectionAC = new AbortController();
  const { signal } = selectionAC;
  let isPointerDown = false;

  document.addEventListener("pointerdown", () => { isPointerDown = true; }, { signal });
  document.addEventListener("pointerup", () => { isPointerDown = false; textLayers.forEach(reset); }, { signal });
  window.addEventListener("blur", () => { isPointerDown = false; textLayers.forEach(reset); }, { signal });
  document.addEventListener("keyup", () => { if (!isPointerDown) textLayers.forEach(reset); }, { signal });

  let prevRange: Range | null = null;
  document.addEventListener(
    "selectionchange",
    () => {
      const selection = document.getSelection();
      if (!selection || selection.rangeCount === 0) {
        textLayers.forEach(reset);
        return;
      }

      // Mark the text layers the selection currently touches; reset the rest.
      const activeLayers = new Set<HTMLElement>();
      for (let i = 0; i < selection.rangeCount; i++) {
        const range = selection.getRangeAt(i);
        for (const div of textLayers.keys()) {
          if (!activeLayers.has(div) && range.intersectsNode(div)) activeLayers.add(div);
        }
      }
      for (const [div, endDiv] of textLayers) {
        if (activeLayers.has(div)) div.classList.add("selecting");
        else reset(endDiv, div);
      }

      // Firefox constrains multi-column selection natively; the reposition
      // below is only needed on Chromium/WebKit.
      if (isFirefox === undefined) {
        const first = textLayers.keys().next().value;
        isFirefox = first
          ? getComputedStyle(first).getPropertyValue("-moz-user-select") === "none"
          : false;
      }
      if (isFirefox) {
        prevRange = selection.getRangeAt(0).cloneRange();
        return;
      }

      const range = selection.getRangeAt(0);
      const modifyStart =
        prevRange !== null &&
        (range.compareBoundaryPoints(Range.END_TO_END, prevRange) === 0 ||
          range.compareBoundaryPoints(Range.START_TO_END, prevRange) === 0);

      let anchor: Node | null = modifyStart ? range.startContainer : range.endContainer;
      if (anchor.nodeType === Node.TEXT_NODE) anchor = anchor.parentNode;
      let anchorEl = anchor as Element | null;
      if (anchorEl?.classList?.contains("highlight")) {
        anchorEl = anchorEl.parentNode as Element | null;
      }
      if (!anchorEl) {
        prevRange = range.cloneRange();
        return;
      }

      // A caret at offset 0 belongs to the previous drawable node.
      if (!modifyStart && range.endOffset === 0) {
        let node: Node = anchorEl;
        do {
          while (!node.previousSibling) {
            if (!node.parentNode) break;
            node = node.parentNode;
          }
          if (!node.previousSibling) break;
          node = node.previousSibling;
        } while (!node.childNodes.length);
        anchorEl = node as Element;
      }

      const parentTextLayer = anchorEl.parentElement?.closest(".textLayer") as HTMLElement | null;
      const endDiv = parentTextLayer ? textLayers.get(parentTextLayer) : undefined;
      if (endDiv && parentTextLayer && anchorEl.parentElement) {
        endDiv.style.width = parentTextLayer.style.width;
        endDiv.style.height = parentTextLayer.style.height;
        endDiv.style.userSelect = "text";
        anchorEl.parentElement.insertBefore(endDiv, modifyStart ? anchorEl : anchorEl.nextSibling);
      }
      prevRange = range.cloneRange();
    },
    { signal },
  );
}

export function registerTextLayerSelection(div: HTMLElement): () => void {
  const end = document.createElement("div");
  end.className = "endOfContent";
  div.append(end);
  const onMouseDown = () => div.classList.add("selecting");
  div.addEventListener("mousedown", onMouseDown);
  textLayers.set(div, end);
  enableGlobalSelectionListener();

  return () => {
    div.removeEventListener("mousedown", onMouseDown);
    textLayers.delete(div);
    end.remove();
    if (textLayers.size === 0) {
      selectionAC?.abort();
      selectionAC = null;
    }
  };
}
