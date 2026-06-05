import { useState, useEffect, useRef } from "react";
import { getKomoditas, getKategori, getTren, getTrenFunFact, withTimeout } from "../services/api";
import {
  TrendingUp, TrendingDown, ChevronDown, ChevronUp,
  Sparkles,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import ChartSkeleton from "../components/ChartSkeleton";
import ErrorCard from "../components/ErrorCard";

// ── Helpers ────────────────────────────────────────────────────────

function formatRp(val) {
  if (!val && val !== 0) return "Rp 0";
  return "Rp " + Math.round(val).toLocaleString("id-ID");
}

function formatTanggal(str) {
  const d = new Date(str);
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "2-digit" });
}

function formatPersen(val) {
  if (val === null || val === undefined || isNaN(val)) return null;
  const n = parseFloat(val).toFixed(1);
  return val > 0 ? `+${n}%` : `${n}%`;
}

// ── Custom Tooltip ─────────────────────────────────────────────────

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "white",
      border: "1px solid #e8f5e9",
      borderRadius: 12,
      padding: "12px 16px",
      boxShadow: "0 8px 32px rgba(27,67,50,.12)",
      fontSize: 13,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 8, color: "#6b7280", fontSize: 12 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{
          display: "flex", alignItems: "center", gap: 8,
          color: p.name === "historis" ? "#1B4332" : "#F9A825",
          fontWeight: 700, marginBottom: 3,
        }}>
          <span style={{
            width: 10, height: 10, borderRadius: "50%",
            background: p.name === "historis" ? "#1B4332" : "#F9A825",
            display: "inline-block", flexShrink: 0,
          }} />
          <span style={{ color: "#9ca3af", fontWeight: 500, fontSize: 12 }}>
            {p.name === "historis" ? "Historis" : "Forecast"}:
          </span>
          <span style={{ fontFamily: "monospace" }}>{formatRp(p.value)}</span>
        </div>
      ))}
    </div>
  );
};

// ── Highlights helper ──────────────────────────────────────────────

function getHighlights(allData) {
  const changes = [];
  allData.forEach(({ nama, historis, satuan }) => {
    if (historis.length < 2) return;
    const last  = historis[historis.length - 1].harga;
    const prev  = historis[historis.length - 2].harga;
    const delta = ((last - prev) / prev) * 100;
    changes.push({ nama, last, delta, satuan });
  });
  changes.sort((a, b) => b.delta - a.delta);
  return {
    naik:  changes.filter((c) => c.delta > 0).slice(0, 3),
    turun: changes.filter((c) => c.delta < 0).slice(0, 3),
  };
}

// ── Main Component ─────────────────────────────────────────────────

export default function TrenHarga() {
  const [kategoriList,      setKategoriList]      = useState([]);
  const [selectedKat,       setSelectedKat]       = useState(null);
  const [dropdownOpen,      setDropdownOpen]      = useState(false);
  const [komoditasList,     setKomoditasList]     = useState([]);
  const [selectedKomoditas, setSelectedKomoditas] = useState(null);
  const [trenData,          setTrenData]          = useState(null);
  const [trenError,         setTrenError]         = useState(null);
  const [loading,           setLoading]           = useState(false);
  const [selectedHari,      setSelectedHari]      = useState(90);
  const [highlights,        setHighlights]        = useState(null);
  const [loadingHL,         setLoadingHL]         = useState(true);
  const [apiStatus,         setApiStatus]         = useState("checking");
  const [funFact,           setFunFact]           = useState(null);
  const [loadingFF,         setLoadingFF]         = useState(false);
  const dropdownRef = useRef(null);

  // ── Load kategori ──
  useEffect(() => {
    getKategori().then(setKategoriList).catch(() => {});
  }, []);

  // ── Close dropdown on outside click ──
  useEffect(() => {
    const fn = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  // ── Load highlights dengan health check ──
  useEffect(() => {
    const proxyKomoditas = [
      "beras_premium", "cabe_merah_keriting", "daging_ayam_ras",
      "bawang_merah", "minyak_goreng_curah", "telur_ayam_ras",
    ];

    const run = async () => {
      try {
        await withTimeout(getKategori(), 3000);
        setApiStatus("online");
      } catch {
        setApiStatus("offline");
        setLoadingHL(false);
        return;
      }

      const results = [];
      for (const id of proxyKomoditas) {
        try {
          const data = await withTimeout(getTren(id, 7), 2000);
          results.push({
            nama: data.nama_komoditas,
            historis: data.data_historis,
            satuan: data.satuan || null,
          });
        } catch {
          // skip
        }
      }
      setHighlights(getHighlights(results));
      setLoadingHL(false);
    };

    run();
  }, []);

  // ── Pilih kategori ──
  const pilihKategori = async (kat) => {
    setSelectedKat(kat);
    setDropdownOpen(false);
    setSelectedKomoditas(null);
    setTrenData(null);
    setTrenError(null);
    setFunFact(null);
    const data = await getKomoditas(kat.kategori);
    setKomoditasList(data);
    if (data.length > 0) pilihKomoditas(data[0], selectedHari);
  };

  // ── Pilih komoditas ──
  const pilihKomoditas = async (item, hari = selectedHari) => {
    setSelectedKomoditas(item);
    setLoading(true);
    setTrenData(null);
    setTrenError(null);
    setFunFact(null);

    try {
      const data = await getTren(item.id, hari);
      setTrenData(data);

      setLoadingFF(true);
      getTrenFunFact(item.id)
        .then(setFunFact)
        .catch(() => setFunFact(null))
        .finally(() => setLoadingFF(false));

    } catch (err) {
      try {
        await withTimeout(getKategori(), 2000);
        setTrenError("model");
      } catch {
        setTrenError("network");
      }
    }
    setLoading(false);
  };

  const gantiRentang = async (hari) => {
    setSelectedHari(hari);
    if (selectedKomoditas) await pilihKomoditas(selectedKomoditas, hari);
  };

  // ── Chart data ──
  const chartData = trenData ? [
    ...trenData.data_historis.map((d) => ({
      tanggal: formatTanggal(d.tanggal), historis: d.harga,
    })),
    ...trenData.forecast_30_hari.map((d) => ({
      tanggal: formatTanggal(d.tanggal), forecast: d.harga,
    })),
  ] : [];

  const getTrendInfo = () => {
    if (!trenData?.data_historis?.length) return null;
    const hist  = trenData.data_historis;
    const first = hist[0].harga;
    const last  = hist[hist.length - 1].harga;
    const diff  = last - first;
    const pct   = ((diff / first) * 100).toFixed(1);
    return { diff, pct, up: diff > 0 };
  };

  const trend       = getTrendInfo();
  const lastHarga   = trenData?.data_historis?.slice(-1)[0]?.harga;
  const nextHarga   = trenData?.forecast_30_hari?.[29]?.harga;
  const forecastPct = trenData?.forecast_trend_percentage ?? null;
  const satuanLabel = selectedKomoditas?.satuan || trenData?.satuan || "kg";

return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');

        .tr-root { font-family: 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif; }

        @keyframes tr-shimmer {
          0%   { background-position: -600px 0; }
          100% { background-position:  600px 0; }
        }
        @keyframes tr-pulse {
          0%,100% { opacity:1; transform:scale(1); }
          50%      { opacity:.5; transform:scale(.85); }
        }
        @keyframes tr-ff-in {
          from { opacity:0; transform:translateY(12px); }
          to   { opacity:1; transform:none; }
        }
        @keyframes tr-sparkle {
          0%,100% { transform:rotate(0deg) scale(1); }
          25%      { transform:rotate(-8deg) scale(1.1); }
          75%      { transform:rotate(8deg) scale(1.1); }
        }

        .tr-shimmer-el {
          background: linear-gradient(90deg,#f0fdf4 25%,#d1fae5 50%,#f0fdf4 75%);
          background-size: 600px 100%;
          animation: tr-shimmer 1.5s ease-in-out infinite;
          border-radius: 8px;
        }
        .tr-pulse-dot { animation: tr-pulse 1.2s ease-in-out infinite; }
        .tr-ff-card   { animation: tr-ff-in .45s cubic-bezier(.22,1,.36,1) forwards; }
        .tr-sparkle   { animation: tr-sparkle 2.5s ease-in-out infinite; }

        .tr-stat-card {
          background: white;
          border-radius: 18px;
          border: 1.5px solid #e8f5e9;
          padding: 20px 22px;
          position: relative; overflow: hidden;
          transition: all .25s ease;
          box-shadow: 0 2px 12px rgba(27,67,50,.05);
        }
        .tr-stat-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 28px rgba(27,67,50,.1);
          border-color: #a7f3d0;
        }

        /* ── ARSITEKTUR LAYOUT 2 KOLOM (RASIO 25% : 75%) ── */
        .tr-dashboard-layout {
          display: grid;
          grid-template-columns: 25% 1fr; /* Kolom kiri diperbesar, sisi kanan disesuaikan mengecil */
          gap: 24px;
          align-items: start;
        }

        @media (max-width: 1100px) {
          .tr-dashboard-layout {
            grid-template-columns: 1fr; /* Otomatis susun vertikal jika layar terlalu sempit */
          }
        }

        .tr-kat-item {
          padding: 10px 18px;
          cursor: pointer; font-size: 13.5px;
          display: flex; justify-content: space-between; align-items: center;
          border-bottom: 1px solid #f0f9f4;
          transition: background .15s;
          font-family: inherit;
        }
        .tr-kat-item:hover { background: #f8fdf9; }

        .tr-kom-item {
          padding: 11px 18px;
          cursor: pointer; font-size: 13.5px;
          font-weight: 400; color: #6b7280;
          background: transparent;
          border-left: 3px solid transparent;
          transition: all .15s;
          font-family: inherit;
        }
        .tr-kom-item.active {
          font-weight: 700; color: #1B4332;
          background: #f0fdf4;
          border-left-color: #1B4332;
        }
        .tr-kom-item:hover:not(.active) { background: #f8fdf9; color: #1B4332; }

        .tr-range-btn {
          padding: 5px 14px; border-radius: 20px;
          border: 1.5px solid #e8f5e9;
          background: white; color: #6b7280;
          font-size: 12px; font-weight: 500; cursor: pointer;
          font-family: inherit;
          transition: all .18s;
        }
        .tr-stat-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 14px;
        }

        @media (max-width: 860px) {
          .tr-stat-grid { grid-template-columns: repeat(2, 1fr); }
        }

        @media (max-width: 560px) {
          .tr-stat-grid { grid-template-columns: 1fr; }
        }
        .tr-range-btn.active {
          background: #1B4332; color: white;
          border-color: #1B4332; font-weight: 700;
        }
        .tr-range-btn:hover:not(.active) { border-color: #1B4332; color: #1B4332; }
      `}</style>

      <div className="tr-root">
        {/* ── 1. PAGE HEADER ── */}
        <div style={{ marginBottom: 26 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 11,
              background: "linear-gradient(135deg, #1B4332, #2d6a4f)",
              display: "flex", alignItems: "center", justifyContent: "center",
              boxShadow: "0 4px 14px rgba(27,67,50,.25)",
            }}>
              <TrendingUp size={18} color="white" />
            </div>
            <div>
              <h1 style={{
                fontSize: 26, fontWeight: 900, color: "#1B4332",
                letterSpacing: "-.4px", lineHeight: 1.1,
              }}>Market Trends</h1>
              <p style={{ fontSize: 13, color: "#9ca3af", marginTop: 2 }}>
                Tren harga historis dan prediksi 30 hari ke depan
              </p>
            </div>
          </div>
        </div>

        {/* Layout Utama Berpasangan */}
        <div className="tr-dashboard-layout">

          {/* ══════════ SEKSI NAVIGASI PENAPIS DATA (KIRI) ══════════ */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, width: "100%" }}>
            
            {/* Dropdown Kategori */}
            <div ref={dropdownRef} style={{ position: "relative", width: "100%" }}>
              <div onClick={() => setDropdownOpen(!dropdownOpen)} style={{
                background: "white", borderRadius: 14,
                border: `1.5px solid ${dropdownOpen ? "#1B4332" : "#e8f5e9"}`,
                padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between",
                cursor: "pointer", userSelect: "none", boxShadow: "0 2px 12px rgba(27,67,50,.05)", transition: "all .18s",
              }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: selectedKat ? "#1B4332" : "#9ca3af" }}>
                  {selectedKat ? selectedKat.kategori : "Pilih Kategori"}
                </span>
                <div style={{ width: 28, height: 28, borderRadius: 8, background: dropdownOpen ? "#1B4332" : "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center", transition: "all .18s" }}>
                  {dropdownOpen ? <ChevronUp size={14} color="white" /> : <ChevronDown size={14} color="#1B4332" />}
                </div>
              </div>

              {dropdownOpen && (
                <div style={{ position: "absolute", top: "calc(100% + 8px)", left: 0, right: 0, zIndex: 50, background: "white", borderRadius: 14, border: "1.5px solid #e8f5e9", boxShadow: "0 8px 32px rgba(27,67,50,.12)", maxHeight: 280, overflowY: "auto" }}>
                  {kategoriList.map((k) => (
                    <div key={k.kategori} className="tr-kat-item" onClick={() => pilihKategori(k)} style={{ background: selectedKat?.kategori === k.kategori ? "#f0fdf4" : undefined, color: selectedKat?.kategori === k.kategori ? "#1B4332" : "#374151", fontWeight: selectedKat?.kategori === k.kategori ? 700 : 500 }}>
                      <span>{k.kategori}</span>
                      <span style={{ fontSize: 11, background: "#f0fdf4", color: "#1B4332", fontWeight: 700, padding: "2px 8px", borderRadius: 20, border: "1px solid #a7f3d0" }}>{k.jumlah_komoditas}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* List Sub-Komoditas */}
            {komoditasList.length > 0 && (
              <div style={{ background: "white", borderRadius: 14, border: "1.5px solid #e8f5e9", maxHeight: 280, overflowY: "auto", boxShadow: "0 2px 12px rgba(27,67,50,.05)", padding: "6px 0" }}>
                {komoditasList.map((item) => (
                  <div key={item.id} className={`tr-kom-item${selectedKomoditas?.id === item.id ? " active" : ""}`} onClick={() => pilihKomoditas(item)}>
                    {item.nama}
                  </div>
                ))}
              </div>
            )}

            {/* Kartu Informasi Fun Fact (Nempel manis di panel kiri bawah) */}
            {selectedKomoditas && (
              <div style={{ width: "100%" }}>
                {loadingFF ? (
                  <div style={{ background: "linear-gradient(135deg, #1B4332, #2d6a4f)", borderRadius: 16, padding: "18px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                      <div className="tr-shimmer-el" style={{ width: 24, height: 24, borderRadius: "50%" }} />
                      <div className="tr-shimmer-el" style={{ width: 100, height: 12 }} />
                    </div>
                    <div className="tr-shimmer-el" style={{ width: "100%", height: 11, marginBottom: 8 }} />
                    <div className="tr-shimmer-el" style={{ width: "85%", height: 11 }} />
                  </div>
                ) : funFact ? (
                  <div className="tr-ff-card" style={{
                    background: "linear-gradient(145deg, #1B4332 0%, #2d6a4f 70%, #1a5c3f 100%)",
                    borderRadius: 16, padding: "20px 18px",
                    boxShadow: "0 8px 28px rgba(27,67,50,.2)",
                    position: "relative", overflow: "hidden",
                    border: "1.5px solid #2d6a4f"
                  }}>
                    <div style={{ position: "absolute", top: -20, right: -20, width: 80, height: 80, borderRadius: "50%", background: "rgba(249,168,37,.08)", pointerEvents: "none" }} />
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                      <Sparkles size={16} color="#F9A825" className="tr-sparkle" />
                      <span style={{ fontSize: 15, fontWeight: 800, color: "#F9A825", textTransform: "uppercase", letterSpacing: "1.5px" }}>Tahukah Kamu?</span>
                    </div>
                    <p style={{ fontSize: 14, color: "rgba(255,255,255,.92)", lineHeight: 1.65, fontWeight: 500, marginBottom: 14, textAlign: "justify", padding: "0 4px" }}>
                      {funFact.teks_fun_fact || funFact.funfact || funFact.fun_fact || funFact.deskripsi || "Data menarik untuk komoditas ini sedang tidak tersedia."}
                    </p>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "rgba(255,255,255,.45)" }}>
                      <span>📍</span>
                      <span style={{ fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
                      {funFact.label_cerdas_ml || "Surabaya"}</span>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {/* ══════════ PANEL DATA UTAMA & STAT CARDS (KANAN) ══════════ */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
            
            {/* 4 Elemen Stat Cards */}
            {trenData && (
              <div className="tr-stat-grid">
                {/* 1 — Harga Terakhir */}
                <div className="tr-stat-card">
                  <div style={{ fontSize: 11, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 10 }}>Harga Terakhir</div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: "#1B4332", letterSpacing: "-.5px", marginBottom: 4 }}>{formatRp(lastHarga)}</div>
                  <div style={{ fontSize: 11.5, color: "#9ca3af" }}>per {satuanLabel}</div>
                  <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: "linear-gradient(90deg, #1B4332, #2d6a4f)", borderRadius: "0 0 18px 18px" }} />
                </div>

                {/* 2 — Prediksi 30 Hari */}
                <div className="tr-stat-card" style={{ borderColor: "#fde68a" }}>
                  <div style={{ fontSize: 11, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 10 }}>Prediksi 30 Hari</div>
                  <div style={{ fontSize: 22, fontWeight: 900, color: "#b45309", letterSpacing: "-.5px", marginBottom: 4 }}>{formatRp(nextHarga)}</div>
                  <div style={{ fontSize: 11.5, color: "#9ca3af" }}>per {satuanLabel}</div>
                  <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: "linear-gradient(90deg, #F9A825, #f59f00)", borderRadius: "0 0 18px 18px" }} />
                </div>

                {/* 3 — Tren Historis */}
                <div className="tr-stat-card" style={{ borderColor: trend?.up ? "#fecaca" : "#a7f3d0" }}>
                  <div style={{ fontSize: 11, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 10 }}>Tren Historis</div>
                  {trend ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      {trend.up ? <TrendingUp size={20} color="#dc2626" /> : <TrendingDown size={20} color="#1B4332" />}
                      <span style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-.5px", color: trend.up ? "#dc2626" : "#1B4332" }}>{trend.up ? "+" : ""}{trend.pct}%</span>
                    </div>
                  ) : <div style={{ fontSize: 22, fontWeight: 900, color: "#9ca3af" }}>—</div>}
                  <div style={{ fontSize: 11.5, color: "#9ca3af" }}>{trend?.up ? "harga naik" : "harga turun"}</div>
                  <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: trend?.up ? "linear-gradient(90deg, #dc2626, #ef4444)" : "linear-gradient(90deg, #1B4332, #2d6a4f)", borderRadius: "0 0 18px 18px" }} />
                </div>

                {/* 4 — Tren Forecast */}
                <div className="tr-stat-card" style={{ borderColor: forecastPct !== null && forecastPct > 0 ? "#fecaca" : "#a7f3d0", background: forecastPct !== null ? (forecastPct > 0 ? "#fffbfb" : "#f8fdfb") : "white" }}>
                  <div style={{ fontSize: 11, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 10 }}>Tren Forecast</div>
                  {forecastPct !== null ? (
                    <>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        {forecastPct > 0 ? <TrendingUp size={20} color="#dc2626" /> : <TrendingDown size={20} color="#1B4332" />}
                        <span style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-.5px", color: forecastPct > 0 ? "#dc2626" : "#1B4332" }}>{formatPersen(forecastPct)}</span>
                      </div>
                      <div style={{ fontSize: 11.5, color: "#9ca3af" }}>30 hari ke depan</div>
                    </>
                  ) : (
                    <>
                      <div style={{ fontSize: 22, fontWeight: 900, color: "#9ca3af" }}>—</div>
                      <div style={{ fontSize: 11.5, color: "#9ca3af" }}>tidak tersedia</div>
                    </>
                  )}
                  <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 3, background: forecastPct !== null && forecastPct > 0 ? "linear-gradient(90deg, #f97316, #ef4444)" : "linear-gradient(90deg, #3b82f6, #06b6d4)", borderRadius: "0 0 18px 18px" }} />
                </div>
              </div>
            )}

            {/* Blok Panel Utama Line Chart */}
            {!selectedKomoditas ? (
              <div style={{ background: "white", borderRadius: 18, border: "1.5px solid #e8f5e9", boxShadow: "0 2px 12px rgba(27,67,50,.05)", overflow: "hidden" }}>
                <div style={{ padding: "18px 22px", borderBottom: "1px solid #f0fdf4", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: "#1B4332" }}>Sorotan Harga Hari Ini</div>
                    <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>Pilih kategori dan komoditas di kiri untuk melihat grafik lengkap</div>
                  </div>
                  {!loadingHL && apiStatus === "online" && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "11.5px", color: "#1B4332", fontWeight: 600, background: "#f0fdf4", padding: "5px 12px", borderRadius: 20, border: "1px solid #a7f3d0" }}>
                      <span className="tr-pulse-dot" style={{ width: 7, height: 7, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} /> Live
                    </div>
                  )}
                </div>

                {loadingHL ? (
                  <div style={{ padding: "32px 22px", textAlign: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "center", color: "#9ca3af", fontSize: "13.5px" }}>
                      <span className="tr-pulse-dot" style={{ width: 8, height: 8, borderRadius: "50%", background: "#1B4332", display: "inline-block" }} /> Memeriksa koneksi...
                    </div>
                  </div>
                ) : apiStatus === "offline" ? (
                  <div style={{ padding: "16px 22px" }}><ErrorCard type="network" compact /></div>
                ) : (!highlights?.naik?.length && !highlights?.turun?.length) ? (
                  <div style={{ padding: "16px 22px" }}><ErrorCard type="highlights" /></div>
                ) : (
                  <div style={{ padding: "20px 22px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 20 }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 800, color: "#dc2626", marginBottom: 12, textTransform: "uppercase", letterSpacing: "1px" }}>
                        <TrendingUp size={13} /> Harga Naik
                      </div>
                      {highlights.naik.map((item) => (
                        <div key={item.nama} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: "#fff5f5", borderRadius: 12, marginBottom: 8, border: "1px solid #fecaca" }}>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 700, color: "#1a1a1a" }}>{item.nama}</div>
                            <div style={{ fontSize: 11.5, color: "#9ca3af", fontFamily: "monospace" }}>{formatRp(item.last)}{item.satuan ? `/${item.satuan}` : ""}</div>
                          </div>
                          <span style={{ fontSize: 12, fontWeight: 800, color: "#dc2626", background: "#fee2e2", padding: "3px 10px", borderRadius: 20 }}>+{item.delta.toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>

                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 800, color: "#1B4332", marginBottom: 12, textTransform: "uppercase", letterSpacing: "1px" }}>
                        <TrendingDown size={13} /> Harga Turun
                      </div>
                      {highlights.turun.map((item) => (
                        <div key={item.nama} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: "#f0fdf4", borderRadius: 12, marginBottom: 8, border: "1px solid #a7f3d0" }}>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 700, color: "#1a1a1a" }}>{item.nama}</div>
                            <div style={{ fontSize: 11.5, color: "#9ca3af", fontFamily: "monospace" }}>{formatRp(item.last)}{item.satuan ? `/${item.satuan}` : ""}</div>
                          </div>
                          <span style={{ fontSize: 12, fontWeight: 800, color: "#1B4332", background: "#bbf7d0", padding: "3px 10px", borderRadius: 20 }}>{item.delta.toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : loading ? (
              <ChartSkeleton komoditasNama={selectedKomoditas?.nama} />
            ) : trenData ? (
              <div style={{ background: "white", borderRadius: 18, border: "1.5px solid #e8f5e9", boxShadow: "0 2px 12px rgba(27,67,50,.05)", overflow: "hidden" }}>
                <div style={{ padding: "16px 22px", borderBottom: "1px solid #f0fdf4", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
                  <div>
                    <span style={{ fontSize: 15, fontWeight: 800, color: "#1B4332" }}>Tren Harga — {selectedKomoditas.nama}</span>
                    <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 12 }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 5, color: "#6b7280" }}><span style={{ width: 18, height: 3, background: "#1B4332", display: "inline-block", borderRadius: 2 }} /> Historis</span>
                      <span style={{ display: "flex", alignItems: "center", gap: 5, color: "#6b7280" }}><span style={{ width: 18, height: 3, background: "#F9A825", display: "inline-block", borderRadius: 2, backgroundImage: "repeating-linear-gradient(90deg,#F9A825 0px,#F9A825 4px,transparent 4px,transparent 8px)" }} /> Forecast</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    {[{ label: "1 Bln", hari: 30 }, { label: "3 Bln", hari: 90 }, { label: "6 Bln", hari: 180 }, { label: "1 Thn", hari: 365 }].map((opt) => (
                      <button key={opt.hari} className={`tr-range-btn${selectedHari === opt.hari ? " active" : ""}`} onClick={() => gantiRentang(opt.hari)}>{opt.label}</button>
                    ))}
                  </div>
                </div>
                <div style={{ padding: "18px 22px 12px" }}>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={chartData} margin={{ top: 5, right: 16, bottom: 5, left: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0fdf4" />
                      <XAxis dataKey="tanggal" tick={{ fontSize: 11, fill: "#9ca3af" }} tickLine={false} axisLine={{ stroke: "#e8f5e9" }} interval={Math.floor(chartData.length / 7)} />
                      <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip content={<CustomTooltip />} />
                      <ReferenceLine x={chartData[trenData.data_historis.length - 1]?.tanggal} stroke="#e8f5e9" strokeDasharray="4 4" label={{ value: "Hari ini", fontSize: 11, fill: "#9ca3af" }} />
                      <Line type="monotone" dataKey="historis" stroke="#1B4332" strokeWidth={2.5} dot={false} connectNulls activeDot={{ r: 5, fill: "#1B4332", stroke: "white", strokeWidth: 2 }} />
                      <Line type="monotone" dataKey="forecast" stroke="#F9A825" strokeWidth={2.5} strokeDasharray="6 4" dot={false} connectNulls activeDot={{ r: 5, fill: "#F9A825", stroke: "white", strokeWidth: 2 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : (
              <ErrorCard type={trenError || "generic"} onRetry={() => pilihKomoditas(selectedKomoditas, selectedHari)} />
            )}
          </div>

        </div>
      </div>
    </>
  );
}