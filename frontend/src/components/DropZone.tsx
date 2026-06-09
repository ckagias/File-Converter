import { useRef, useState } from "react";

const STYLES = {
  zone: "relative border-2 border-dashed border-[var(--border)] rounded-lg p-10 text-center cursor-pointer transition-colors",
  zoneDragging: "border-[var(--accent)] bg-[var(--accent-muted)]",
  zoneIdle: "hover:border-[var(--accent)] hover:bg-[var(--surface-raised)]",
  hiddenInput: "hidden",
  icon: "text-[var(--muted-fg)] text-3xl mb-3 select-none",
  heading: "text-sm font-medium text-[var(--foreground)] mb-1",
  sub: "text-xs text-[var(--muted-fg)]",
  hint: "mt-3 text-xs text-[var(--muted-fg)] font-mono",
};

interface Props {
  onFiles: (files: File[]) => void;
  accept: string;
}

export default function DropZone({ onFiles, accept }: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) onFiles(files);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    /* only clear when leaving the zone entirely */
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragging(false);
    }
  }

  function handleClick() {
    inputRef.current?.click();
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFiles(files);
    e.target.value = "";
  }

  const zoneClass = [STYLES.zone, dragging ? STYLES.zoneDragging : STYLES.zoneIdle].join(" ");

  return (
    <div
      className={zoneClass}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={handleClick}
      role="button"
      aria-label="Upload files"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") handleClick();
      }}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={accept}
        className={STYLES.hiddenInput}
        onChange={handleInputChange}
        tabIndex={-1}
      />
      <div className={STYLES.icon}>↑</div>
      <p className={STYLES.heading}>Drop files here or click to browse</p>
      <p className={STYLES.sub}>Multiple files supported</p>
      {accept && (
        <p className={STYLES.hint}>
          Accepted: {accept.split(",").map((s) => s.trim()).join(", ")}
        </p>
      )}
    </div>
  );
}