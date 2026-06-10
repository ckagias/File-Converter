import { useState, useEffect, useRef, useCallback } from "react";
import { getFormats, uploadFile, downloadFile, type Job } from "../api";
import { PALETTES, usePalette } from "../theme";
import FormatSelector from "./FormatSelector";
import DropZone from "./DropZone";

// ── File entry ────────────────────────────────────────────────────────────────

type FileStatus = "queued" | "uploading" | "converting" | "done" | "error";

interface FileEntry {
  id: string;
  file: File;
  job: Job | null;
  status: FileStatus;
  progress: number;
  errorMessage: string | null;
  outputFilename: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileIcon({ ext }: { ext: string }) {
  const color = extColor(ext);
  return (
    <div style={{
      width: 36, height: 36, borderRadius: 6, flexShrink: 0,
      background: `${color}18`, border: `0.5px solid ${color}40`,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <span style={{ fontSize: "9px", fontWeight: 600, color, letterSpacing: "0.02em" }}>
        {ext.slice(0, 4).toUpperCase()}
      </span>
    </div>
  );
}

function extColor(ext: string): string {
  const map: Record<string, string> = {
    pdf: "#e05252", doc: "#4a7ef5", docx: "#4a7ef5",
    jpg: "#e8924a", jpeg: "#e8924a", png: "#3ecf6e",
    mp3: "#a855f7", mp4: "#f59e0b", zip: "#5b6ef5",
    csv: "#3ecf6e", txt: "#888888",
  };
  return map[ext.toLowerCase()] ?? "#5a5a5a";
}

function Spinner() {
  return (
    <svg className="spin" width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="5.5" stroke="var(--cf-accent)" strokeWidth="1.5" strokeDasharray="22" strokeDashoffset="8" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path d="M2.5 7l3 3 6-6" stroke="var(--cf-success)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="5.5" stroke="var(--cf-error)" strokeWidth="1.5" />
      <path d="M7 4.5v3M7 9.5v.5" stroke="var(--cf-error)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 3500);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div
      className="fade-in"
      style={{
        position: "fixed", top: "16px", left: "50%", transform: "translateX(-50%)",
        background: "#3a0f0f", border: "0.5px solid var(--cf-error)",
        borderRadius: "8px", padding: "10px 16px",
        display: "flex", alignItems: "center", gap: "8px",
        fontSize: "13px", color: "var(--cf-error)", fontWeight: 500,
        zIndex: 100, whiteSpace: "nowrap", boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
      }}
    >
      <ErrorIcon />
      {message}
      <button
        onClick={onDismiss}
        style={{
          background: "none", border: "none", cursor: "pointer",
          color: "var(--cf-error)", padding: "0 0 0 4px",
          fontSize: "14px", lineHeight: 1, opacity: 0.7, fontFamily: "inherit",
        }}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}

// ── Error humanizer ───────────────────────────────────────────────────────────

function humanizeError(raw: string): string {
  if (!raw) return "Conversion failed. The file may be corrupted or an unsupported variant.";
  const r = raw.toLowerCase();
  if (r.includes("libreoffice")) return "Document conversion failed. File may be password-protected or corrupted.";
  if (r.includes("ffmpeg") && r.includes("timed out")) return "Video conversion timed out. Try a smaller file or different format.";
  if (r.includes("zip bomb")) return "Archive rejected: uncompressed size is too large.";
  if (r.includes("timed out or worker crashed")) return "Server ran out of resources. Try again in a few minutes.";
  if (r.includes("magic byte") || r.includes("file content does not match")) return "File content doesn't match the selected format. Check the file isn't renamed.";
  if (r.includes("too large")) return raw;
  return "Conversion failed. The file may be corrupted or an unsupported variant.";
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [formats, setFormats] = useState<Record<string, string[]>>({});
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const { currentIndex, setPalette } = usePalette();
  const abortRefs = useRef<Record<string, AbortController>>({});

  useEffect(() => {
    getFormats().then((fmts) => {
      const keys = Object.keys(fmts);
      if (keys.length > 0) {
        setSource(keys[0]);
        setTarget((fmts[keys[0]] ?? [])[0] ?? "");
      }
      setFormats(fmts);
    });
    return () => { Object.values(abortRefs.current).forEach((c) => c.abort()); };
  }, []);

  function handleSourceChange(s: string) {
    setSource(s);
    const available = formats[s] ?? [];
    setTarget((prev) => available.includes(prev) ? prev : (available[0] ?? ""));
  }

  function updateEntry(id: string, patch: Partial<FileEntry>) {
    setEntries((prev) => prev.map((e) => e.id === id ? { ...e, ...patch } : e));
  }

  const pollWithBackoff = useCallback((
    entryId: string,
    jobId: string,
    signal: AbortSignal,
    deadline: number,
    delay = 1000,
    pollProgress = 50,
  ) => {
    if (signal.aborted) return;
    const POLL_MAX_DELAY = 15000;
    const POLL_BACKOFF = 1.5;
    const REQUEST_TIMEOUT = 8000;

    const handle = setTimeout(async () => {
      if (signal.aborted) return;

      if (Date.now() > deadline) {
        updateEntry(entryId, { status: "error", errorMessage: "Conversion timed out. Try a smaller file." });
        return;
      }

      const reqController = new AbortController();
      const reqTimeout = setTimeout(() => reqController.abort(), REQUEST_TIMEOUT);

      try {
        const res = await fetch(`/api/files/${jobId}/status`, { signal: reqController.signal });
        clearTimeout(reqTimeout);
        const data = await res.json() as { status: string; output_filename: string | null; error_message: string | null };

        if (data.status === "done") {
          updateEntry(entryId, { status: "done", progress: 100, outputFilename: data.output_filename });
        } else if (data.status === "error") {
          updateEntry(entryId, {
            status: "error",
            progress: 0,
            errorMessage: humanizeError(data.error_message ?? ""),
          });
        } else {
          const nextProgress = Math.min(95, pollProgress + 2);
          updateEntry(entryId, { progress: nextProgress });
          const nextDelay = Math.min(delay * POLL_BACKOFF, POLL_MAX_DELAY);
          pollWithBackoff(entryId, jobId, signal, deadline, nextDelay, nextProgress);
        }
      } catch (err) {
        clearTimeout(reqTimeout);
        if (signal.aborted) return;
        if (err instanceof DOMException && err.name === "AbortError") {
          pollWithBackoff(entryId, jobId, signal, deadline, Math.min(delay * POLL_BACKOFF, POLL_MAX_DELAY), pollProgress);
        } else {
          updateEntry(entryId, { status: "error", errorMessage: "Lost connection to server" });
        }
      }
    }, delay);

    signal.addEventListener("abort", () => clearTimeout(handle));
  }, []);

  async function processEntry(entry: FileEntry, targetFmt: string) {
    const controller = new AbortController();
    abortRefs.current[entry.id] = controller;
    const deadline = Date.now() + 30 * 60 * 1000;

    try {
      updateEntry(entry.id, { status: "uploading", progress: 0 });
      const job = await uploadFile(
        entry.file,
        targetFmt,
        (pct) => updateEntry(entry.id, { progress: pct * 0.5 }),
        controller.signal,
      );
      updateEntry(entry.id, { job, status: "converting", progress: 50 });
      pollWithBackoff(entry.id, job.id, controller.signal, deadline);
    } catch (err) {
      if (controller.signal.aborted) return;
      updateEntry(entry.id, {
        status: "error",
        errorMessage: err instanceof Error ? humanizeError(err.message) : "Upload failed",
      });
    }
  }

  async function handleFiles(files: File[]) {
    if (!target) return;
    if (files.length > 1) {
      setToast("Only one file at a time — please drop a single file.");
      return;
    }
    const file = files[0];
    if (!file) return;
    const fileExt = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (source && fileExt !== source.toLowerCase()) {
      setToast(`Expected a .${source} file but got .${fileExt || "unknown"}.`);
      return;
    }
    const entry: FileEntry = {
      id: crypto.randomUUID(),
      file,
      job: null,
      status: "queued" as FileStatus,
      progress: 0,
      errorMessage: null,
      outputFilename: null,
    };
    setEntries([entry]);
    setTimeout(() => processEntry(entry, target), 0);
  }

  async function handleDownload(entry: FileEntry) {
    if (!entry.job) return;
    try {
      const blob = await downloadFile(entry.job.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = entry.outputFilename ?? `converted.${entry.job.target_format}`;
      a.click();
      URL.revokeObjectURL(url);
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
    } catch (err) {
      updateEntry(entry.id, { status: "error", errorMessage: err instanceof Error ? err.message : "Download failed" });
    }
  }

  function handleRetry(entry: FileEntry) {
    abortRefs.current[entry.id]?.abort();
    delete abortRefs.current[entry.id];
    const fresh = { ...entry, status: "queued" as FileStatus, progress: 0, errorMessage: null, job: null, outputFilename: null };
    updateEntry(entry.id, fresh);
    processEntry(fresh, target);
  }

  function reset() {
    Object.values(abortRefs.current).forEach((c) => c.abort());
    abortRefs.current = {};
    setEntries([]);
  }

  const isProcessing = entries.some((e) => e.status === "queued" || e.status === "uploading" || e.status === "converting");
  const hasEntries = entries.length > 0;

  return (
    <div style={{ minHeight: "100dvh", background: "var(--cf-bg)", display: "flex", flexDirection: "column" }}>
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}

      {/* ── Topbar ── */}
      <header style={{
        height: 48,
        borderBottom: "0.5px solid var(--cf-border)",
        padding: "0 20px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexShrink: 0,
      }}>
        {/* Left: converting badge */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {isProcessing && (
            <div className="fade-in" style={{
              display: "flex", alignItems: "center", gap: "5px",
              fontSize: "11px", fontWeight: 500, color: "var(--cf-accent)",
            }}>
              <Spinner />
              Converting…
            </div>
          )}
        </div>

        {/* Right: theme switcher */}
        <div style={{ display: "flex", gap: "5px", alignItems: "center" }}>
          {PALETTES.map((p, i) => (
            <button
              key={p.name}
              onClick={() => setPalette(i)}
              aria-label={`Switch to ${p.name} theme`}
              title={p.name}
              style={{
                width: 20, height: 20, borderRadius: "50%",
                background: p.accent,
                border: currentIndex === i ? `2px solid var(--cf-text)` : "2px solid transparent",
                cursor: "pointer", padding: 0, flexShrink: 0,
                transition: "border-color 0.15s, transform 0.12s",
                transform: currentIndex === i ? "scale(1.15)" : "scale(1)",
              }}
            />
          ))}
        </div>
      </header>

      {/* ── Main ── */}
      <main style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "32px 24px" }}>
        <div style={{ width: "100%", maxWidth: 620 }}>

          {/* ── Idle state ── */}
          {!hasEntries && (
            <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
              <div>
                <h1 style={{ fontSize: "32px", fontWeight: 600, color: "var(--cf-text)", letterSpacing: "-0.03em", marginBottom: "10px", lineHeight: 1.2 }}>
                  File Converter
                </h1>
                <p style={{ fontSize: "15px", lineHeight: "1.7", color: "var(--cf-text)", opacity: 0.7, maxWidth: 460 }}>
                  Images, documents, audio, video, archives. Pick your formats, drop a file. Deleted from the server the moment you download.
                </p>
              </div>

              {Object.keys(formats).length > 0 && (
                <FormatSelector
                  formats={formats}
                  source={source}
                  target={target}
                  onSourceChange={handleSourceChange}
                  onTargetChange={setTarget}
                />
              )}
              <DropZone onFiles={handleFiles} accept={source ? `.${source}` : ""} formats={formats} source={source} />
            </div>
          )}

          {/* ── Processing / Results state ── */}
          {hasEntries && (
            <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {entries.map((entry) => (
                <FileCard
                  key={entry.id}
                  entry={entry}
                  onDownload={handleDownload}
                  onRetry={handleRetry}
                />
              ))}

              <div style={{ textAlign: "center", marginTop: "8px" }}>
                <button
                  onClick={reset}
                  style={{
                    background: "transparent",
                    border: "0.5px solid var(--cf-border)",
                    borderRadius: "8px",
                    cursor: "pointer",
                    color: "var(--cf-text)",
                    fontSize: "12px",
                    fontWeight: 500,
                    fontFamily: "inherit",
                    padding: "7px 16px",
                    transition: "border-color 0.15s, color 0.15s",
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--cf-accent)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--cf-accent)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--cf-border)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--cf-text)"; }}
                >
                  Convert another file
                </button>
              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}

// ── File card ─────────────────────────────────────────────────────────────────

function ProgressBar({ isActive, isError, progress, color }: { isActive: boolean; isError: boolean; progress: number; color: string }) {
  return (
    <div style={{
      height: 2, borderRadius: 1, overflow: "hidden",
      background: "var(--cf-border)", marginTop: "12px",
      position: "relative",
    }}>
      {isActive ? (
        <div
          className="progress-indeterminate"
          style={{
            position: "absolute", top: 0, left: 0,
            width: "30%", height: "100%",
            background: color, borderRadius: 1,
          }}
        />
      ) : (
        <div style={{
          width: isError ? "100%" : `${progress}%`, height: "100%",
          background: color, borderRadius: 1,
          transition: "width 0.3s ease",
        }} />
      )}
    </div>
  );
}

function FileCard({
  entry,
  onDownload,
  onRetry,
}: {
  entry: FileEntry;
  onDownload: (e: FileEntry) => void;
  onRetry: (e: FileEntry) => void;
}) {
  const ext = entry.file.name.split(".").pop() ?? "";
  const isDone = entry.status === "done";
  const isError = entry.status === "error";
  const isActive = entry.status === "converting" || entry.status === "uploading";
  const isQueued = entry.status === "queued";

  const barColor = isDone ? "var(--cf-success)" : isError ? "var(--cf-error)" : "var(--cf-accent)";

  return (
    <div
      style={{
        background: "var(--cf-surface)",
        border: "0.5px solid var(--cf-border)",
        borderRadius: "10px",
        padding: "14px 16px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <FileIcon ext={isDone ? (entry.outputFilename?.split(".").pop() ?? ext) : ext} />

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: "13px", fontWeight: 500, color: "var(--cf-text)",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            marginBottom: "2px",
          }}>
            {isDone ? (entry.outputFilename ?? entry.file.name) : entry.file.name}
          </div>
          <div style={{ fontSize: "11px", color: "var(--cf-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
            <span>{formatBytes(entry.file.size)}</span>
            <span style={{ opacity: 0.4 }}>·</span>
            {isQueued && <span className="pulse-dot" />}
            <span style={{ color: isDone ? "var(--cf-success)" : isError ? "var(--cf-error)" : "var(--cf-muted)" }}>
              {statusLabel(entry.status, entry.errorMessage)}
            </span>
          </div>
        </div>

        <div style={{ flexShrink: 0 }}>
          {isDone && <CheckIcon />}
          {isError && <ErrorIcon />}
          {isActive && <Spinner />}
        </div>

        {isDone && (
          <button
            onClick={() => onDownload(entry)}
            style={{
              background: "transparent",
              border: "0.5px solid var(--cf-border)",
              borderRadius: "6px",
              color: "var(--cf-text)",
              fontSize: "11px", fontWeight: 500, fontFamily: "inherit",
              padding: "5px 10px", cursor: "pointer",
              transition: "border-color 0.15s, color 0.15s",
              flexShrink: 0,
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--cf-accent)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--cf-accent)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--cf-border)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--cf-text)"; }}
          >
            Download
          </button>
        )}
        {isError && (
          <button
            onClick={() => onRetry(entry)}
            style={{
              background: "transparent",
              border: "0.5px solid var(--cf-error)",
              borderRadius: "6px",
              color: "var(--cf-error)",
              fontSize: "11px", fontWeight: 500, fontFamily: "inherit",
              padding: "5px 10px", cursor: "pointer",
              transition: "opacity 0.15s",
              flexShrink: 0,
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = "0.75"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = "1"; }}
          >
            Retry
          </button>
        )}
      </div>

      {!isQueued && (
        <ProgressBar isActive={isActive} isError={isError} progress={entry.progress} color={barColor} />
      )}

      {isError && entry.errorMessage && (
        <p style={{
          fontSize: "11px", color: "var(--cf-error)",
          marginTop: "8px", opacity: 0.85,
        }}>
          {entry.errorMessage}
        </p>
      )}
    </div>
  );
}

function statusLabel(status: FileStatus, errorMessage?: string | null): string {
  switch (status) {
    case "queued":     return "Queued";
    case "uploading":  return "Uploading…";
    case "converting": return "Converting…";
    case "done":       return "Ready to download";
    case "error":      return errorMessage === "Lost connection to server" ? "Network error" : "Conversion failed";
  }
}
