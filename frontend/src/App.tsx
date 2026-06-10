import { ThemeProvider } from "./theme";
import Dashboard from "./components/Dashboard";
import ErrorBoundary from "./components/ErrorBoundary";

export default function App() {
  return (
    <ThemeProvider>
      <ErrorBoundary>
        <Dashboard />
      </ErrorBoundary>
    </ThemeProvider>
  );
}