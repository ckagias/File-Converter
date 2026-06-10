import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(err: unknown): State {
    const message = err instanceof Error ? err.message : String(err);
    return { hasError: true, message };
  }

  reset = () => this.setState({ hasError: false, message: "" });

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div style={{
        minHeight: "100dvh", background: "var(--cf-bg)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "32px 24px",
      }}>
        <div style={{
          maxWidth: 420, width: "100%", textAlign: "center",
          display: "flex", flexDirection: "column", alignItems: "center", gap: "16px",
        }}>
          <svg width="32" height="32" viewBox="0 0 14 14" fill="none">
            <circle cx="7" cy="7" r="5.5" stroke="var(--cf-error)" strokeWidth="1.5" />
            <path d="M7 4.5v3M7 9.5v.5" stroke="var(--cf-error)" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <p style={{ fontSize: "14px", color: "var(--cf-text)", fontWeight: 500, margin: 0 }}>
            Something went wrong
          </p>
          {this.state.message && (
            <p style={{ fontSize: "12px", color: "var(--cf-muted)", margin: 0 }}>
              {this.state.message}
            </p>
          )}
          <button
            onClick={this.reset}
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
            }}
          >
            Try again
          </button>
        </div>
      </div>
    );
  }
}