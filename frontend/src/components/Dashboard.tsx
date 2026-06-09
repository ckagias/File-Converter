import { useState, useEffect, useRef } from "react";
import { getFormats, uploadFile, downloadFile, type Job } from "../api";
import FormatSelector from "./FormatSelector";
import DropZone from "./DropZone";

const STYLES = {
  root: "min-h-[100dvh] bg-[var(--background)] flex flex-col",
  header: "border-b border-[var(--border)] bg-[var(--surface)] px-6 h-14 flex items-center shrink-0",
  appName: "text-sm font-bold text-[var(--foreground)] tracking-tight",
  main: "flex-1 flex items-center justify-center px-6 py-8",
  card: "w-full max-w-lg flex flex-col gap-6",
  errorMsg: "text-xs text-[var(--danger)] border border-[var(--danger)] border-opacity-20 bg-red-950/10 rounded px-3 py-2 font-mono",
  result: "bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6 flex flex-col gap-4",
  resultFilename: "text-sm font-mono text-[var(--foreground)] truncate",
  resultMeta: "text-xs font-mono text-[var(--muted-fg)]",
  actions: "flex gap-3",
  downloadBtn: "flex-1 bg-[var(--accent)] hover:opacity-90 active:scale-[0.98] text-white text-sm font-medium py-2 rounded-md transition-all cursor-pointer text-center",
  resetBtn: "flex-1 border border-[var(--border)] hover:border-[var(--accent)] text-[var(--muted-fg)] hover:text-[var(--foreground)] text-sm py-2 rounded-md transition-colors cursor-pointer bg-transparent",
  converting: "flex items-center gap-2 text-sm text-[var(--accent)] font-mono",
  dot: "w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse",
};

type State =
  | { phase: "idle" }
  | { phase: "converting"; job: Job }
  | { phase: "done"; job: Job }
  | { phase: "error"; message: string };

export default function Dashboard() {
  const [formats, setFormats] = useState<Record<string, string[]>>({});
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [state, setState] = useState<State>({ phase: "idle" });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getFormats().then((fmts) => {
      const keys = Object.keys(fmts);
      if (keys.length > 0) {
        setSource(keys[0]);
        setTarget((fmts[keys[0]] ?? [])[0] ?? "");
      }
      setFormats(fmts);
    });
    return () => stopPolling();
  }, []);

  function stopPolling() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function handleFiles(files: File[]) {
    const file = files[0];
    if (!file || !target) return;

    setState({ phase: "converting", job: {} as Job });

    try {
      const job = await uploadFile(file, target);
      setState({ phase: "converting", job });

      pollRef.current = setInterval(async () => {
        try {
          const { data } = await fetch(`/api/files/${job.id}/status`).then(async (r) => ({
            data: await r.json() as { status: string; output_filename: string | null },
          }));
          if (data.status === "done") {
            stopPolling();
            setState({ phase: "done", job: { ...job, output_filename: data.output_filename } });
          } else if (data.status === "error") {
            stopPolling();
            setState({ phase: "error", message: "Conversion failed" });
          }
        } catch {
          stopPolling();
          setState({ phase: "error", message: "Lost connection to server" });
        }
      }, 2000);
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "Upload failed" });
    }
  }

  async function handleDownload() {
    if (state.phase !== "done") return;
    try {
      const blob = await downloadFile(state.job.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = state.job.output_filename ?? `converted.${state.job.target_format}`;
      a.click();
      URL.revokeObjectURL(url);
      setState({ phase: "idle" });
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "Download failed" });
    }
  }

  function handleSourceChange(s: string) {
    setSource(s);
    setTarget((formats[s] ?? [])[0] ?? "");
  }

  function reset() {
    stopPolling();
    setState({ phase: "idle" });
  }

  return (
    <div className={STYLES.root}>
      <header className={STYLES.header}>
        <span className={STYLES.appName}>File Converter</span>
      </header>

      <main className={STYLES.main}>
        <div className={STYLES.card}>
          {state.phase === "idle" && (
            <>
              {Object.keys(formats).length > 0 && (
                <FormatSelector
                  formats={formats}
                  source={source}
                  target={target}
                  onSourceChange={handleSourceChange}
                  onTargetChange={setTarget}
                />
              )}
              <DropZone onFiles={handleFiles} accept={source ? `.${source}` : ""} />
            </>
          )}

          {state.phase === "converting" && (
            <div className={STYLES.converting}>
              <span className={STYLES.dot} />
              Converting...
            </div>
          )}

          {state.phase === "done" && (
            <div className={STYLES.result}>
              <div>
                <p className={STYLES.resultFilename}>{state.job.original_filename}</p>
                <p className={STYLES.resultMeta}>
                  {state.job.source_format.toUpperCase()} → {state.job.target_format.toUpperCase()}
                </p>
              </div>
              <div className={STYLES.actions}>
                <button type="button" className={STYLES.downloadBtn} onClick={handleDownload}>
                  Download
                </button>
                <button type="button" className={STYLES.resetBtn} onClick={reset}>
                  Convert another file
                </button>
              </div>
            </div>
          )}

          {state.phase === "error" && (
            <>
              <div className={STYLES.errorMsg}>{state.message}</div>
              <button type="button" className={STYLES.resetBtn} onClick={reset}>
                Try again
              </button>
            </>
          )}
        </div>
      </main>
    </div>
  );
}