const BLOCKED = new Set(["I", "J", "C", "K"]);

export function protectPage() {
  document.addEventListener("contextmenu", (e) => e.preventDefault());
  document.addEventListener("keydown", (e) => {
    const k = (e.key || "").toUpperCase();
    const ctrl = e.ctrlKey || e.metaKey;
    if (k === "F12" || (ctrl && e.shiftKey && BLOCKED.has(k)) || (ctrl && (k === "U" || k === "S"))) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);
}
