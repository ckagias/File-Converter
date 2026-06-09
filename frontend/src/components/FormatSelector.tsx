const STYLES = {
  root: "flex items-center gap-3",
  label: "text-xs font-medium text-[var(--muted-fg)] uppercase tracking-wider mb-1",
  selectGroup: "flex flex-col",
  select:
    "bg-[var(--surface-raised)] border border-[var(--border)] text-[var(--foreground)] text-sm rounded-md px-3 py-2 focus:outline-none focus:border-[var(--accent)] cursor-pointer transition-colors min-w-[120px]",
  arrow: "text-[var(--muted-fg)] text-lg font-light select-none mt-5",
};

interface Props {
  formats: Record<string, string[]>;
  source: string;
  target: string;
  onSourceChange: (source: string) => void;
  onTargetChange: (target: string) => void;
}

export default function FormatSelector({
  formats,
  source,
  target,
  onSourceChange,
  onTargetChange,
}: Props) {
  const sourceOptions = Object.keys(formats);
  const targetOptions = formats[source] ?? [];

  function handleSourceChange(e: React.ChangeEvent<HTMLSelectElement>) {
    onSourceChange(e.target.value);
  }

  return (
    <div className={STYLES.root}>
      <div className={STYLES.selectGroup}>
        <span className={STYLES.label}>From</span>
        <select
          className={STYLES.select}
          value={source}
          onChange={handleSourceChange}
          aria-label="Source format"
        >
          {sourceOptions.map((fmt) => (
            <option key={fmt} value={fmt}>
              {fmt.toUpperCase()}
            </option>
          ))}
        </select>
      </div>

      <span className={STYLES.arrow}>→</span>

      <div className={STYLES.selectGroup}>
        <span className={STYLES.label}>To</span>
        <select
          className={STYLES.select}
          value={target}
          onChange={(e) => onTargetChange(e.target.value)}
          aria-label="Target format"
          disabled={targetOptions.length === 0}
        >
          {targetOptions.map((fmt) => (
            <option key={fmt} value={fmt}>
              {fmt.toUpperCase()}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}