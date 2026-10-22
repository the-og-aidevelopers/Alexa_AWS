import { useEffect, useRef } from "react";

export default function Modal({ open, onClose, wide = false, label, children }) {
  const ref = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`modal${wide ? " wide" : ""}`}
      aria-label={label}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === ref.current) onClose(); }}
    >
      {open ? children : null}
    </dialog>
  );
}
