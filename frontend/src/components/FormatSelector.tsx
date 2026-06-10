import { HiChevronUpDown } from "react-icons/hi2";

interface Props {
  formats: Record<string, string[]>;
  source: string;
  target: string;
  onSourceChange: (source: string) => void;
  onTargetChange: (target: string) => void;
}

export default function FormatSelector({ formats, source, target, onSourceChange, onTargetChange }: Props) {
  const sourceOptions = Object.keys(formats);
  const targetOptions = formats[source] ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <label htmlFor="source-format" style={{ fontSize: "12px", color: "var(--cf-muted)", letterSpacing: "0.03em" }}>
        Convert file
      </label>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <SelectField
          id="source-format"
          value={source}
          options={sourceOptions}
          onChange={onSourceChange}
          ariaLabel="Source format"
        />

        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, color: "var(--cf-muted)" }}>
          <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
        </svg>

        <SelectField
          value={target}
          options={targetOptions}
          onChange={onTargetChange}
          ariaLabel="Target format"
          disabled={targetOptions.length === 0}
        />
      </div>
    </div>
  );
}

function SelectField({
  id,
  value,
  options,
  onChange,
  ariaLabel,
  disabled,
}: {
  id?: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  ariaLabel: string;
  disabled?: boolean;
}) {
  return (
    <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={ariaLabel}
        disabled={disabled}
        style={{
          appearance: "none",
          WebkitAppearance: "none",
          background: "var(--cf-surface)",
          border: "0.5px solid var(--cf-border)",
          color: "var(--cf-text)",
          fontSize: "13px",
          fontFamily: "inherit",
          fontWeight: 500,
          borderRadius: "8px",
          padding: "7px 32px 7px 10px",
          cursor: disabled ? "not-allowed" : "pointer",
          minWidth: "100px",
          transition: "border-color 0.15s",
          outline: "none",
          opacity: disabled ? 0.4 : 1,
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = "var(--cf-accent)"; }}
        onBlur={(e) => { e.currentTarget.style.borderColor = "var(--cf-border)"; }}
      >
        {options.map((fmt) => (
          <option key={fmt} value={fmt}>{fmt.toLowerCase()}</option>
        ))}
      </select>
      <HiChevronUpDown
        size={14}
        style={{
          position: "absolute", right: 9, pointerEvents: "none",
          color: "var(--cf-muted)", flexShrink: 0,
        }}
      />
    </div>
  );
}
