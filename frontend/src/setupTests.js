import "@testing-library/jest-dom/vitest";

// jsdom has no <dialog> modal support.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal() { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close() { this.removeAttribute("open"); };
}
if (!window.HTMLCanvasElement.prototype.getContext.__patched) {
  window.HTMLCanvasElement.prototype.getContext = () => null;
  window.HTMLCanvasElement.prototype.getContext.__patched = true;
}
