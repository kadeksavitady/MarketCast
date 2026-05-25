import { useState, useEffect } from "react";
import { Search } from "lucide-react";

export default function Topbar({ onSearch }) {
  const [query, setQuery] = useState("");
  const [tanggal, setTanggal] = useState("");

  useEffect(() => {
    const now = new Date();
    const formatted = now.toLocaleDateString("id-ID", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
    setTanggal(formatted);
  }, []);

  const handleChange = (e) => {
    setQuery(e.target.value);
    if (onSearch) onSearch(e.target.value);
  };

  return (
    <header style={styles.topbar}>
      <div style={styles.searchBox}>
        <Search size={15} color="var(--text-muted)" />
        <input
          style={styles.searchInput}
          placeholder="Cari bahan pokok..."
          value={query}
          onChange={handleChange}
        />
      </div>
      <div style={styles.dateChip}>
        <span style={styles.dateText}>{tanggal}</span>
      </div>
    </header>
  );
}

const styles = {
  topbar: {
    background: "var(--card-bg)",
    borderBottom: "1px solid var(--border)",
    padding: "0 28px",
    height: 60,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    position: "sticky",
    top: 0,
    zIndex: 99,
  },
  searchBox: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "var(--bg)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: "8px 14px",
    width: 300,
  },
  searchInput: {
    border: "none",
    background: "transparent",
    fontFamily: "inherit",
    fontSize: 13.5,
    color: "var(--text-main)",
    outline: "none",
    width: "100%",
  },
  dateChip: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: "var(--bg)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: "6px 14px",
  },
  dateText: {
    fontSize: 13,
    color: "var(--text-sub)",
    fontWeight: 500,
  },
};