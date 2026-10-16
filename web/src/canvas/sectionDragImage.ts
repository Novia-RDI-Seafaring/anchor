/**
 * What a section dragged off a document card looks like while it is carried.
 *
 * The browser's own drag picture is the region's box at the size it shows on
 * the card, which is small, and the card then lands at a default size with
 * its corner at the pointer: what was let go was not what landed. Here the
 * section is cut from the card's page image and drawn at the size the new
 * card will have at the current zoom, held at the same point the reader
 * pressed. The returned grab point and width go with the drop, so the card
 * lands exactly under the preview, as it does when carried from the viewer.
 */
export function sectionDragImage(
  e: { clientX: number; clientY: number; currentTarget: EventTarget; dataTransfer: DataTransfer },
  page: HTMLImageElement | null,
  landedWidth: number | undefined,
): { grabX: number; grabY: number; width: number } | null {
  const region = e.currentTarget as HTMLElement;
  if (!page || !page.naturalWidth || !landedWidth) return null;
  const box = region.getBoundingClientRect();
  const pageBox = page.getBoundingClientRect();
  if (box.width <= 0 || box.height <= 0 || pageBox.width <= 0) return null;
  // The canvas zoom, read off the card: its drawn width over its own width.
  const card = region.closest<HTMLElement>(".react-flow__node");
  const zoom = card && card.offsetWidth > 0 ? card.getBoundingClientRect().width / card.offsetWidth : 1;
  const width = landedWidth * zoom;
  const k = width / box.width;
  const scale = page.naturalWidth / pageBox.width;
  const cut = document.createElement("canvas");
  cut.width = Math.max(1, Math.round(width));
  cut.height = Math.max(1, Math.round(box.height * k));
  cut.getContext("2d")?.drawImage(
    page,
    (box.left - pageBox.left) * scale, (box.top - pageBox.top) * scale,
    box.width * scale, box.height * scale,
    0, 0, cut.width, cut.height,
  );
  Object.assign(cut.style, {
    position: "fixed", top: "-10000px", left: "-10000px",
    border: "2px solid rgb(14 165 233)", borderRadius: "4px", background: "white",
  });
  document.body.appendChild(cut);
  const grabX = Math.min(cut.width, Math.max(0, (e.clientX - box.left) * k));
  const grabY = Math.min(cut.height, Math.max(0, (e.clientY - box.top) * k));
  e.dataTransfer.setDragImage(cut, grabX, grabY);
  window.setTimeout(() => cut.remove(), 0);
  return { grabX, grabY, width };
}
