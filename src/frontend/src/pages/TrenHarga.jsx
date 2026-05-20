import { useState, useEffect } from "react";
import { getKomoditas, getKategori, getTren } from "../services/api";
import { TrendingUp, TrendingDown, Minus, BarChart2 } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend
} from "recharts";

function formatRp(val) {
  if (!val && val !== 0) return "Rp 0";
  return "Rp " + Math.round(val).toLocaleString("id-ID");
}

function formatTanggal(str) {
  const d = new Date(str);
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "2-digit" });
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "white", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 14px", boxShadow: "var(--shadow-md)", fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 6, color: "var(--text-sub)" }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, fontWeight: 600 }}>
          {p.name === "historis" ? "Historis" : "Forecast"}: {formatRp(p.value)}
        </div>
      ))}
    </div>
  );
};

export default function TrenHarga() {
  const [kategoriList, setKategoriList] = useState([]);
  const [komoditasList, setKomoditasList] = useState([]);
  const [selectedKat, setSelectedKat] = useState(null);
  const [selectedKomoditas, setSelectedKomoditas] = useState(null);
  const [trenData, setTrenData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedHari, setSelectedHari] = useState(90);

  useEffect(() => {
    getKategori().then(setKategoriList);
  }, []);

  const pilihKategori = async (kat) => {
    setSelectedKat(kat);
    setSelectedKomoditas(null);
    setTrenData(null);
    const data = await getKomoditas(kat.kategori);
    setKomoditasList(data);
  };

  const pilihKomoditas = async (item, hari = selectedHari) => {
    setSelectedKomoditas(item);
    setLoading(true);
    setTrenData(null);
    try {
      const data = await getTren(item.id, hari);
      setTrenData(data);
    } catch {
      setTrenData(null);
    }
    setLoading(false);
  };

  const gantiRentang = async (hari) => {
  setSelectedHari(hari);
  if (selectedKomoditas) {
    await pilihKomoditas(selectedKomoditas, hari);
  }
};

  // Gabungkan data historis dan forecast untuk chart
  const chartData = trenData ? [
    ...trenData.data_historis.map((d) => ({
      tanggal: formatTanggal(d.tanggal),
      historis: d.harga,
    })),
    ...trenData.forecast_30_hari.map((d) => ({
      tanggal: formatTanggal(d.tanggal),
      forecast: d.harga,
    })),
  ] : [];

  // Hitung tren
  const getTrendInfo = () => {
    if (!trenData?.data_historis?.length) return null;
    const hist = trenData.data_historis;
    const first = hist[0].harga;
    const last = hist[hist.length - 1].harga;
    const diff = last - first;
    const pct = ((diff / first) * 100).toFixed(1);
    return { diff, pct, up: diff > 0 };
  };

  const trend = getTrendInfo();
  const lastHarga = trenData?.data_historis?.slice(-1)[0]?.harga;
  const nextHarga = trenData?.forecast_30_hari?.[29]?.harga;

  return (
    <div>
      <h1 style={{ marginBottom: 4 }}>Market Trends</h1>
      <p style={{ color: "var(--text-sub)", fontSize: 14, marginBottom: 24 }}>
        Tren harga historis dan prediksi 30 hari ke depan
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 20, alignItems: "start" }}>

        {/* PANEL KIRI — Pilih Komoditas */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Pilih Kategori */}
          <div style={card}>
            <div style={cardHeader}>
              <span style={cardTitle}>Pilih Kategori</span>
            </div>
            <div style={{ padding: "8px 0" }}>
              {kategoriList.map((k) => (
                <div key={k.kategori}
                  onClick={() => pilihKategori(k)}
                  style={{
                    ...navItem,
                    ...(selectedKat?.kategori === k.kategori ? navItemActive : {}),
                  }}>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{k.kategori}</span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{k.jumlah_komoditas}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Pilih Komoditas */}
          {komoditasList.length > 0 && (
            <div style={card}>
              <div style={cardHeader}>
                <span style={cardTitle}>Pilih Komoditas</span>
              </div>
              <div style={{ padding: "8px 0" }}>
                {komoditasList.map((item) => (
                  <div key={item.id}
                    onClick={() => pilihKomoditas(item)}
                    style={{
                      ...navItem,
                      ...(selectedKomoditas?.id === item.id ? navItemActive : {}),
                    }}>
                    <span style={{ fontSize: 13, fontWeight: 500 }}>{item.nama}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* PANEL KANAN — Chart */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {!selectedKomoditas ? (
            <div style={{ ...card, padding: "80px 20px", textAlign: "center", color: "var(--text-muted)" }}>
              <BarChart2 size={48} style={{ marginBottom: 16, opacity: 0.3 }} />
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Pilih komoditas</div>
              <div style={{ fontSize: 13 }}>Pilih kategori dan komoditas di panel kiri untuk melihat tren harga</div>
            </div>
          ) : loading ? (
            <div style={{ ...card, padding: "80px 20px", textAlign: "center", color: "var(--text-muted)" }}>
              Memuat data tren...
            </div>
          ) : trenData ? (
            <>
              {/* STAT CARDS */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
                <div style={{ ...card, padding: 18 }}>
                  <div style={{ fontSize: 12, color: "var(--text-sub)", marginBottom: 6 }}>Harga Terakhir</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: "var(--text-main)" }}>{formatRp(lastHarga)}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>per kg</div>
                </div>
                <div style={{ ...card, padding: 18 }}>
                  <div style={{ fontSize: 12, color: "var(--text-sub)", marginBottom: 6 }}>Prediksi 30 Hari</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: "var(--primary-dark)" }}>{formatRp(nextHarga)}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>per kg</div>
                </div>
                <div style={{ ...card, padding: 18 }}>
                  <div style={{ fontSize: 12, color: "var(--text-sub)", marginBottom: 6 }}>Tren 30 Hari</div>
                  {trend && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {trend.up
                        ? <TrendingUp size={20} color="var(--red)" />
                        : trend.diff < 0
                          ? <TrendingDown size={20} color="var(--primary-dark)" />
                          : <Minus size={20} color="var(--text-muted)" />
                      }
                      <span style={{ fontSize: 20, fontWeight: 800, color: trend.up ? "var(--red)" : "var(--primary-dark)" }}>
                        {trend.up ? "+" : ""}{trend.pct}%
                      </span>
                    </div>
                  )}
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>historis</div>
                </div>
              </div>

              {/* CHART */}
              <div style={card}>
                <div style={{ ...cardHeader, flexWrap: "wrap", gap: 12 }}>
                  <span style={cardTitle}>
                    Tren Harga — {selectedKomoditas.nama}
                  </span>

                  {/* Tombol filter rentang waktu */}
                  <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
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
                          padding: "5px 12px",
                          borderRadius: 20,
                          border: "1px solid var(--border)",
                          background: selectedHari === opt.hari ? "var(--primary)" : "white",
                          color: selectedHari === opt.hari ? "white" : "var(--text-sub)",
                          fontSize: 12,
                          fontWeight: selectedHari === opt.hari ? 700 : 500,
                          cursor: "pointer",
                        }}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>

                  {/* Legend */}
                  <div style={{ width: "100%", display: "flex", gap: 16, fontSize: 12 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <span style={{ width: 12, height: 2, background: "var(--primary)", display: "inline-block" }} />
                      Historis
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <span style={{ width: 12, height: 2, background: "var(--accent)", display: "inline-block" }} />
                      Forecast
                    </span>
                  </div>
                </div>
                <div style={{ padding: "20px 20px 10px" }}>
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis
                        dataKey="tanggal"
                        tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                        tickLine={false}
                        interval={Math.floor(chartData.length / 8)}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `${(v/1000).toFixed(0)}k`}
                      />
                      <Tooltip content={<CustomTooltip />} />
                      <ReferenceLine
                        x={chartData[trenData.data_historis.length - 1]?.tanggal}
                        stroke="var(--border)"
                        strokeDasharray="4 4"
                        label={{ value: "Hari ini", fontSize: 11, fill: "var(--text-muted)" }}
                      />
                      <Line
                        type="monotone"
                        dataKey="historis"
                        stroke="var(--primary)"
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                      />
                      <Line
                        type="monotone"
                        dataKey="forecast"
                        stroke="var(--accent)"
                        strokeWidth={2}
                        strokeDasharray="5 5"
                        dot={false}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </>
          ) : (
            <div style={{ ...card, padding: "40px 20px", textAlign: "center", color: "var(--text-muted)" }}>
              Gagal memuat data. Pastikan API berjalan.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const card = { background: "var(--card-bg)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)", overflow: "hidden" };
const cardHeader = { padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 };
const cardTitle = { fontSize: 15, fontWeight: 700 };
const navItem = { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 16px", cursor: "pointer", fontSize: 13, color: "var(--text-sub)", transition: "all 0.15s" };
const navItemActive = { background: "var(--primary-light)", color: "var(--primary-dark)", fontWeight: 700 };
const gantiRentang = async (hari) => {
  setSelectedHari(hari);
  if (selectedKomoditas) {
    await pilihKomoditas(selectedKomoditas, hari);
  }
};