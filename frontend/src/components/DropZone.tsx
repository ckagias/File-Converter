import { useRef, useState } from "react";
import { FiUploadCloud } from "react-icons/fi";

interface Props {
  onFiles: (files: File[]) => void;
  accept: string;
  formats: Record<string, string[]>;
  source: string;
}

export default function DropZone({ onFiles, accept, formats, source }: Props) {
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
    if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFiles(files);
    e.target.value = "";
  }

  const targetFormats = formats[source] ?? [];

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      role="button"
      aria-label="Upload files"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") inputRef.current?.click(); }}
      style={{
        border: `0.5px dashed ${dragging ? "var(--cf-accent)" : "var(--cf-border)"}`,
        borderRadius: "12px",
        padding: "56px 32px",
        textAlign: "center",
        cursor: "pointer",
        background: dragging ? "color-mix(in srgb, var(--cf-accent) 6%, transparent)" : "transparent",
        transition: "border-color 0.15s, background 0.15s",
        userSelect: "none",
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={handleInputChange}
        tabIndex={-1}
      />

      <div style={{ display: "flex", justifyContent: "center", marginBottom: "16px" }}>
        <FiUploadCloud size={36} style={{ color: "var(--cf-muted)" }} />
      </div>

      <p style={{ fontSize: "16px", fontWeight: 500, color: "var(--cf-text)", marginBottom: "8px" }}>
        Drop files here or click to browse
      </p>
      <p style={{ fontSize: "13px", color: "var(--cf-muted)", marginBottom: "22px" }}>
        Max 50 MB
      </p>

      {targetFormats.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", justifyContent: "center" }}>
          {targetFormats.map((fmt) => (
            <span
              key={fmt}
              style={{
                fontSize: "11px",
                fontWeight: 500,
                color: "var(--cf-muted)",
                border: "0.5px solid var(--cf-border)",
                borderRadius: "5px",
                padding: "2px 7px",
                letterSpacing: "0.03em",
              }}
            >
              .{fmt}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
