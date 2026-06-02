import { useState, useEffect } from "react";
import { getKomoditas, getKategori, getTren } from "../services/api";
import {
  TrendingUp, TrendingDown, Minus,
  BarChart2, ChevronDown, ChevronUp,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import ChartSkeleton from "../components/ChartSkeleton";
import ErrorCard from "../components/ErrorCard";
import { withTimeout } from "../services/api";

function formatRp(val) {
  if (!val && val !== 0) return "Rp 0";
  return "Rp " + Math.round(val).toLocaleString("id-ID");
}

function formatTanggal(str) {
  const d = new Date(str);
  return d.toLocaleDateString("id-ID", {
    day: "numeric", month: "short", year: "2-digit",
  });
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "white", border: "1px solid var(--border)",
      borderRadius: 8, padding: "10px 14px",
      boxShadow: "var(--shadow-md)", fontSize: 13,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 6, color: "var(--text-sub)" }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, fontWeight: 600 }}>
          {p.name === "historis" ? "Historis" : "Forecast"}: {formatRp(p.value)}
        </div>
      ))}
    </div>
  );
};

// FIX: tambah satuan ke data highlights agar future-proof saat backend tambah field satuan
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

export default function TrenHarga() {
  const [kategoriList,      setKategoriList]      = useState([]);
  const [selectedKat,       setSelectedKat]       = useState(null);
  const [dropdownOpen,      setDropdownOpen]      = useState(false);
  const [komoditasList,     setKomoditasList]     = useState([]);
  const [selectedKomoditas, setSelectedKomoditas] = useState(null);
  const [trenData,          setTrenData]          = useState(null);
  const [loading,           setLoading]           = useState(false);
  const [trenError,         setTrenError]         = useState(null);
  const [selectedHari,      setSelectedHari]      = useState(90);
  const [highlights,        setHighlights]        = useState(null);
  const [loadingHL,         setLoadingHL]         = useState(true);
  const [apiStatus,         setApiStatus]         = useState("checking");

  useEffect(() => {
    getKategori().then(setKategoriList);
  }, []);

  useEffect(() => {
    const proxyKomoditas = [
      "beras_premium", "cabe_merah_keriting", "daging_ayam_ras",
      "bawang_merah", "minyak_goreng_curah", "telur_ayam_ras",
    ];
    
    const run = async () => {
      // Step 1: cek apakah API hidup dulu (endpoint ringan, tanpa model)
      try {
        await withTimeout(getKategori(), 3000);
        setApiStatus("online");
      } catch {
        setApiStatus("offline");
        setLoadingHL(false);
        return; // API mati, stop di sini
      }

      // Step 2: API hidup, coba load highlights
      const results = [];
      for (const id of proxyKomoditas) {
        try {
          const data = await withTimeout(getTren(id, 7), 3000);
          results.push({
            nama: data.nama_komoditas,
            historis: data.data_historis,
            satuan: data.satuan || null,
          });
        } catch {
          // skip komoditas ini
        }
      }
      setHighlights(getHighlights(results));
      setLoadingHL(false);
    };

    run();
  }, []);

  const pilihKategori = async (kat) => {
    setSelectedKat(kat);
    setDropdownOpen(false);
    setSelectedKomoditas(null);
    setTrenData(null);
    const data = await getKomoditas(kat.kategori);
    setKomoditasList(data);
    if (data.length > 0) {
      pilihKomoditas(data[0], selectedHari);
    }
  };

  const pilihKomoditas = async (item, hari = selectedHari) => {
    setSelectedKomoditas(item);
    setLoading(true);
    setTrenData(null);
    setTrenError(null);
    try {
      const data = await getTren(item.id, hari);
      setTrenData(data);
    } catch (err) {
      // Cek apakah API masih hidup
      try {
        await withTimeout(getKategori(), 2000);
        setTrenError("model"); // API hidup tapi model gagal
      } catch {
        setTrenError("network"); // API mati
      }
    }
    setLoading(false);
  };

  const gantiRentang = async (hari) => {
    setSelectedHari(hari);
    if (selectedKomoditas) await pilihKomoditas(selectedKomoditas, hari);
  };

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

  const trend     = getTrendInfo();
  const lastHarga = trenData?.data_historis?.slice(-1)[0]?.harga;
  const nextHarga = trenData?.forecast_30_hari?.[29]?.harga;

  // FIX: gunakan satuan dari selectedKomoditas (sudah ada di data komoditas)
  // Fallback ke trenData.satuan jika backend sudah menambahkan field tersebut
  const satuanLabel = selectedKomoditas?.satuan || trenData?.satuan || "kg";

  return (
    <div>
      <h1 style={{ marginBottom: 4 }}>Market Trends</h1>
      <p style={{ color: "var(--text-sub)", fontSize: 14, marginBottom: 20 }}>
        Tren harga historis dan prediksi 30 hari ke depan
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 20, alignItems: "start" }}>

        {/* ── PANEL KIRI ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

          {/* Dropdown kategori */}
          <div style={{ position: "relative" }}>
            <div
              onClick={() => setDropdownOpen(!dropdownOpen)}
              style={{
                ...card,
                padding: "12px 16px",
                display: "flex", alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
                userSelect: "none",
              }}
            >
              <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-main)" }}>
                {selectedKat ? selectedKat.kategori : "Pilih Kategori"}
              </span>
              {dropdownOpen
                ? <ChevronUp size={16} color="var(--text-muted)" />
                : <ChevronDown size={16} color="var(--text-muted)" />
              }
            </div>

            {dropdownOpen && (
              <div style={{
                position: "absolute", top: "calc(100% + 6px)",
                left: 0, right: 0, zIndex: 50,
                background: "white",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                boxShadow: "var(--shadow-md)",
                maxHeight: 280, overflowY: "auto",
              }}>
                {kategoriList.map((k) => (
                  <div
                    key={k.kategori}
                    onClick={() => pilihKategori(k)}
                    style={{
                      padding: "10px 14px",
                      cursor: "pointer",
                      fontSize: 13.5,
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      background: selectedKat?.kategori === k.kategori
                        ? "var(--primary-light)" : "white",
                      color: selectedKat?.kategori === k.kategori
                        ? "var(--primary-dark)" : "var(--text-main)",
                      fontWeight: selectedKat?.kategori === k.kategori ? 700 : 400,
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <span>{k.kategori}</span>
                    <span style={{
                      fontSize: 11, color: "var(--text-muted)",
                      background: "var(--bg)", padding: "1px 7px",
                      borderRadius: 20,
                    }}>
                      {k.jumlah_komoditas}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* List komoditas */}
          {komoditasList.length > 0 && (
            <div style={{
              ...card,
              maxHeight: 320, overflowY: "auto",
              padding: "6px 0",
            }}>
              {komoditasList.map((item) => (
                <div
                  key={item.id}
                  onClick={() => pilihKomoditas(item)}
                  style={{
                    padding: "9px 16px",
                    cursor: "pointer",
                    fontSize: 13.5,
                    fontWeight: selectedKomoditas?.id === item.id ? 700 : 400,
                    color: selectedKomoditas?.id === item.id
                      ? "var(--primary-dark)" : "var(--text-sub)",
                    background: selectedKomoditas?.id === item.id
                      ? "var(--primary-light)" : "transparent",
                    borderLeft: selectedKomoditas?.id === item.id
                      ? "3px solid var(--primary)" : "3px solid transparent",
                    transition: "all 0.15s",
                  }}
                >
                  {item.nama}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── PANEL KANAN ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Stat cards */}
          {trenData && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
              <div style={{ ...card, padding: 16 }}>
                <div style={{ fontSize: 11, color: "var(--text-sub)", marginBottom: 4 }}>Harga Terakhir</div>
                <div style={{ fontSize: 20, fontWeight: 800 }}>{formatRp(lastHarga)}</div>
                {/* FIX: gunakan satuanLabel, bukan hardcoded "per kg" */}
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>per {satuanLabel}</div>
              </div>
              <div style={{ ...card, padding: 16 }}>
                <div style={{ fontSize: 11, color: "var(--text-sub)", marginBottom: 4 }}>Prediksi 30 Hari</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: "var(--primary-dark)" }}>{formatRp(nextHarga)}</div>
                {/* FIX: gunakan satuanLabel, bukan hardcoded "per kg" */}
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>per {satuanLabel}</div>
              </div>
              <div style={{ ...card, padding: 16 }}>
                <div style={{ fontSize: 11, color: "var(--text-sub)", marginBottom: 4 }}>Tren Historis</div>
                {trend && (
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {trend.up
                      ? <TrendingUp size={18} color="var(--red)" />
                      : <TrendingDown size={18} color="var(--primary-dark)" />
                    }
                    <span style={{
                      fontSize: 20, fontWeight: 800,
                      color: trend.up ? "var(--red)" : "var(--primary-dark)",
                    }}>
                      {trend.up ? "+" : ""}{trend.pct}%
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Chart area */}
          {!selectedKomoditas ? (
            <div style={card}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
                <div style={{ fontSize: 15, fontWeight: 700 }}>Sorotan Harga Hari Ini</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  Pilih kategori dan komoditas di kiri untuk lihat grafik lengkap
                </div>
              </div>

              {loadingHL ? (
                <div style={{ padding: 40, textAlign: "center" }}>
                  <div style={{ color: "var(--text-muted)", fontSize: 14,
                    display: "flex", alignItems: "center", gap: 8, justifyContent: "center" }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%",
                      background: "var(--primary)", display: "inline-block",
                      animation: "mc-pulse-dot 1.2s ease-in-out infinite" }} />
                    Memeriksa koneksi API...
                  </div>
                </div>
              ) : apiStatus === "offline" ? (
                <div style={{ padding: "16px 20px" }}>
                  <ErrorCard type="network" compact />
                </div>
              ) : (!highlights?.naik?.length && !highlights?.turun?.length) ? (
                <div style={{ padding: "16px 20px" }}>
                  <ErrorCard type="highlights" />
                </div>
              ) : (
                <div style={{ padding: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

                  {/* Naik */}
                  <div>
                    <div style={{
                      display: "flex", alignItems: "center", gap: 6,
                      fontSize: 12, fontWeight: 700,
                      color: "#DC2626", marginBottom: 10,
                    }}>
                      <TrendingUp size={14} />
                      Harga Naik
                    </div>
                    {highlights?.naik?.length ? highlights.naik.map((item) => (
                      <div key={item.nama} style={{
                        display: "flex", justifyContent: "space-between",
                        alignItems: "center", padding: "8px 12px",
                        background: "#FEF2F2", borderRadius: 8,
                        marginBottom: 6,
                      }}>
                        <div>
                          <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-main)" }}>
                            {item.nama}
                          </div>
                          {/* FIX: gunakan item.satuan jika tersedia, fallback tanpa satuan */}
                          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "DM Mono,monospace" }}>
                            {formatRp(item.last)}{item.satuan ? `/${item.satuan}` : ""}
                          </div>
                        </div>
                        <span style={{
                          fontSize: 12, fontWeight: 700,
                          color: "#DC2626",
                          background: "#FEE2E2",
                          padding: "2px 8px", borderRadius: 20,
                        }}>
                          +{item.delta.toFixed(1)}%
                        </span>
                      </div>
                    )) : (
                      <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Tidak ada data</div>
                    )}
                  </div>

                  {/* Turun */}
                  <div>
                    <div style={{
                      display: "flex", alignItems: "center", gap: 6,
                      fontSize: 12, fontWeight: 700,
                      color: "var(--primary-dark)", marginBottom: 10,
                    }}>
                      <TrendingDown size={14} />
                      Harga Turun
                    </div>
                    {highlights?.turun?.length ? highlights.turun.map((item) => (
                      <div key={item.nama} style={{
                        display: "flex", justifyContent: "space-between",
                        alignItems: "center", padding: "8px 12px",
                        background: "var(--primary-light)", borderRadius: 8,
                        marginBottom: 6,
                      }}>
                        <div>
                          <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-main)" }}>
                            {item.nama}
                          </div>
                          {/* FIX: gunakan item.satuan jika tersedia */}
                          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "DM Mono,monospace" }}>
                            {formatRp(item.last)}{item.satuan ? `/${item.satuan}` : ""}
                          </div>
                        </div>
                        <span style={{
                          fontSize: 12, fontWeight: 700,
                          color: "var(--primary-dark)",
                          background: "#BBF7D0",
                          padding: "2px 8px", borderRadius: 20,
                        }}>
                          {item.delta.toFixed(1)}%
                        </span>
                      </div>
                    )) : (
                      <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Tidak ada data</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : loading ? (
            <ChartSkeleton komoditasNama={selectedKomoditas?.nama} />
          ) : trenData ? (
            <div style={card}>
              <div style={{
                padding: "14px 20px",
                borderBottom: "1px solid var(--border)",
                display: "flex", alignItems: "center",
                justifyContent: "space-between", flexWrap: "wrap", gap: 10,
              }}>
                <span style={{ fontSize: 14, fontWeight: 700 }}>
                  Tren Harga — {selectedKomoditas.nama}
                </span>
                <div style={{ display: "flex", gap: 6 }}>
                  {[
                    { label: "1 Bln", hari: 30 },
                    { label: "3 Bln", hari: 90 },
                    { label: "6 Bln", hari: 180 },
                    { label: "1 Thn", hari: 365 },
                  ].map((opt) => (
                    <button
                      key={opt.hari}
                      onClick={() => gantiRentang(opt.hari)}
                      style={{
                        padding: "4px 12px", borderRadius: 20,
                        border: "1px solid var(--border)",
                        background: selectedHari === opt.hari ? "var(--primary)" : "white",
                        color: selectedHari === opt.hari ? "white" : "var(--text-sub)",
                        fontSize: 12, fontWeight: selectedHari === opt.hari ? 700 : 400,
                        cursor: "pointer",
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                <div style={{ width: "100%", display: "flex", gap: 14, fontSize: 12, color: "var(--text-muted)" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 16, height: 2, background: "var(--primary)", display: "inline-block" }} />
                    Historis
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 16, height: 2, background: "var(--accent)", display: "inline-block", borderTop: "2px dashed var(--accent)" }} />
                    Forecast
                  </span>
                </div>
              </div>
              <div style={{ padding: "16px 20px 10px" }}>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={chartData} margin={{ top: 5, right: 16, bottom: 5, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis
                      dataKey="tanggal"
                      tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                      tickLine={false}
                      interval={Math.floor(chartData.length / 7)}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                      tickLine={false} axisLine={false}
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <ReferenceLine
                      x={chartData[trenData.data_historis.length - 1]?.tanggal}
                      stroke="var(--border)" strokeDasharray="4 4"
                      label={{ value: "Hari ini", fontSize: 11, fill: "var(--text-muted)" }}
                    />
                    <Line type="monotone" dataKey="historis" stroke="var(--primary)"
                      strokeWidth={2} dot={false} connectNulls />
                    <Line type="monotone" dataKey="forecast" stroke="var(--accent)"
                      strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <ErrorCard
              type={trenError || "generic"}
              onRetry={() => pilihKomoditas(selectedKomoditas, selectedHari)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

const card = {
  background: "var(--card-bg)",
  borderRadius: "var(--radius)",
  border: "1px solid var(--border)",
  boxShadow: "var(--shadow-sm)",
  overflow: "hidden",
};