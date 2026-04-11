const injectedMarks: Set<HTMLElement> = new Set();

export function getTextLayer(pageEl: HTMLElement): HTMLElement | null {
  return (
    pageEl.querySelector(".react-pdf__Page__textLayer") ??
    pageEl.querySelector(".react-pdf__Page__textContent")
  );
}

export function clearAllMarks() {
  injectedMarks.forEach((mark) => {
    const parent = mark.parentNode;
    if (parent) {
      parent.replaceChild(document.createTextNode(mark.textContent ?? ""), mark);
      parent.normalize();
    }
  });
  injectedMarks.clear();
}

export function applyPageHighlights(pageEl: HTMLElement, query: string): number {
  const textLayer = getTextLayer(pageEl);
  if (!textLayer || !query.trim()) return 0;

  const lowerQuery = query.toLowerCase();
  let count = 0;

  const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  let node: Text | null;

  while ((node = walker.nextNode() as Text | null)) {
    textNodes.push(node);
  }

  textNodes.forEach((textNode) => {
    const text = textNode.textContent ?? "";
    const lowerText = text.toLowerCase();
    const idx = lowerText.indexOf(lowerQuery);

    if (idx === -1) return;

    const before = text.slice(0, idx);
    const match = text.slice(idx, idx + query.length);
    const after = text.slice(idx + query.length);

    const mark = document.createElement("mark");
    mark.textContent = match;
    mark.setAttribute("data-pdf-search", "true");
    mark.style.cssText =
      "background:rgba(59,130,246,0.35);outline:1px solid rgba(59,130,246,0.55);border-radius:2px;color:inherit;";

    injectedMarks.add(mark);

    const parent = textNode.parentNode;
    if (!parent) return;

    if (before) parent.insertBefore(document.createTextNode(before), textNode);
    parent.insertBefore(mark, textNode);
    if (after) parent.insertBefore(document.createTextNode(after), textNode);
    parent.removeChild(textNode);

    count++;
  });

  return count;
}

export function markCurrentPageMatch(pageEl: HTMLElement, isCurrent: boolean) {
  const textLayer = getTextLayer(pageEl);
  textLayer?.querySelectorAll("[data-pdf-search]").forEach((el) => {
    const element = el as HTMLElement;

    if (isCurrent) {
      element.style.background = "rgba(234,179,8,0.55)";
      element.style.outline = "2px solid rgba(234,179,8,0.9)";
    } else {
      element.style.background = "rgba(59,130,246,0.35)";
      element.style.outline = "1px solid rgba(59,130,246,0.55)";
    }
  });
}