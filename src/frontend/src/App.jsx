import { Routes, Route } from "react-router-dom";
import { useSidebar } from "./context/SidebarContext";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Dashboard from "./pages/Dashboard";
import TrenHarga from "./pages/TrenHarga";
import LandingPage from "./pages/LandingPage";

// Layout wrapper untuk halaman app (dengan sidebar + topbar)
function AppShell({ children }) {
  const { collapsed } = useSidebar();
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar />
      <div
        style={{
          marginLeft: collapsed ? 64 : 230,
          flex: 1,
          display: "flex",
          flexDirection: "column",
          transition: "margin-left 0.25s cubic-bezier(0.4,0,0.2,1)",
          minWidth: 0,
        }}
      >
        <Topbar />
        <div style={{ padding: 28 }}>{children}</div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      {/* Landing page — tanpa sidebar */}
      <Route path="/" element={<LandingPage />} />

      {/* App pages — dengan sidebar + topbar */}
      <Route path="/app"  element={<AppShell><Dashboard /></AppShell>} />
      <Route path="/tren" element={<AppShell><TrenHarga /></AppShell>} />
    </Routes>
  );
}