import { Routes, Route } from "react-router-dom";
import { useSidebar } from "./context/SidebarContext";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Dashboard from "./pages/Dashboard";
import TrenHarga from "./pages/TrenHarga";
import FAQ from "./pages/FAQ";

export default function App() {
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
        <div style={{ padding: 28 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/tren" element={<TrenHarga />} />
            <Route path="/faq" element={<FAQ />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}