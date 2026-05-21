import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import Dashboard from "./pages/Dashboard";
import TrenHarga from "./pages/TrenHarga";
import History from "./pages/History";

export default function App() {
  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar />
      <div style={{ marginLeft: 230, flex: 1, display: "flex", flexDirection: "column" }}>
        <Topbar />
        <div style={{ padding: 28 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/tren" element={<TrenHarga />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}