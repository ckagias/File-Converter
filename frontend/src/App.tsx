import { ThemeProvider } from "./theme";
import Dashboard from "./components/Dashboard";

export default function App() {
  return (
    <ThemeProvider>
      <Dashboard />
    </ThemeProvider>
  );
}