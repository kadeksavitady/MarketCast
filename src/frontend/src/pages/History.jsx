import { History as HistoryIcon } from "lucide-react";

export default function History() {
  return (
    <div style={{ textAlign: "center", padding: "80px 20px", color: "var(--text-muted)" }}>
      <HistoryIcon size={48} style={{ marginBottom: 16, opacity: 0.4 }} />
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: "var(--text-sub)" }}>
        Simulation History
      </h2>
      <p style={{ fontSize: 14 }}>Fitur ini akan segera hadir</p>
    </div>
  );
}