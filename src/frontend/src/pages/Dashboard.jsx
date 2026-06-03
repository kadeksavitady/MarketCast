import { useState, useEffect, useRef, useMemo } from "react";
import { getKomoditas, getKategori, predictBelanja } from "../services/api";
import {
  ShoppingCart, Wallet, X, Plus, Minus,
  ChevronRight, Package, Beef, Droplets, Egg,
  Leaf, Fish, Wheat, Cookie, FlameKindling,
  TrendingUp, TrendingDown,
} from "lucide-react";
import SmartSubstitution from "../components/SmartSubstitution";
import { ICON_CATALOG } from "../assets/iconCatalog";
import PredictLoading from "../components/PredictLoading";
import ErrorCard from "../components/ErrorCard";
import { withTimeout } from "../services/api";

// Icon mapping per kategori
const KATEGORI_ICON = {
  "BERAS":        { icon: Wheat,          bg: "#fff7ed", color: "#f59e0b" },
  "DAGING":       { icon: Beef,           bg: "#fef2f2", color: "#ef4444" },
  "MINYAK GORENG":{ icon: Droplets,       bg: "#fefce8", color: "#eab308" },
  "TELUR":        { icon: Egg,            bg: "#fffbeb", color: "#f59e0b" },
  "SAYUR MAYUR":  { icon: Leaf,           bg: "#f0fdf4", color: "#22c55e" },
  "IKAN SEGAR":   { icon: Fish,           bg: "#eff6ff", color: "#3b82f6" },
  "CABE":         { icon: FlameKindling,  bg: "#fef2f2", color: "#ef4444" },
  "BAWANG":       { icon: Leaf,           bg: "#f5f3ff", color: "#8b5cf6" },
  "GULA":         { icon: Cookie,         bg: "#fdf4ff", color: "#a855f7" },
  "TEPUNG":       { icon: Package,        bg: "#f8fafc", color: "#64748b" },
  "SUSU":         { icon: Package,        bg: "#eff6ff", color: "#3b82f6" },
  "GARAM":        { icon: Package,        bg: "#f8fafc", color: "#94a3b8" },
  "MIE INSTAN":   { icon: Package,        bg: "#fff7ed", color: "#f97316" },
  "IKAN ASIN":    { icon: Fish,           bg: "#f0fdf4", color: "#16a34a" },
  "PALAWIJA":     { icon: Wheat,          bg: "#fefce8", color: "#ca8a04" },
  "BARANG PENTING LAINNYA": { icon: Package, bg: "#f1f5f9", color: "#475569" },
};

function formatRp(val) {
  if (!val && val !== 0) return "Rp 0";
  return "Rp " + Math.round(val).toLocaleString("id-ID");
}

export default function Dashboard() {
  const [kategoriList,    setKategoriList]    = useState([]);
  const [selectedKat,     setSelectedKat]     = useState(null);
  const [komoditasList,   setKomoditasList]   = useState([]);
  const [loadingKomoditas,setLoadingKomoditas]= useState(false);
  const [showModal,       setShowModal]       = useState(false);
  const [keranjang,       setKeranjang]       = useState([]);
  const [budget,          setBudget]          = useState(0);
  const [budgetDisplay,   setBudgetDisplay]   = useState("");
  const [hasilPredict,    setHasilPredict]    = useState(null);
  const [loadingPredict,  setLoadingPredict]  = useState(false);
  const [predictError,    setPredictError]    = useState(false);
  const [kategoriError,   setKategoriError]   = useState(false);
  const [toast,           setToast]           = useState({ msg: "", type: "info" });
  const toastTimer = useRef(null);

  useEffect(() => {
    withTimeout(getKategori(), 5000)
      .then(setKategoriList)
      .catch(() => setKategoriError(true));
  }, []);

  const openKategori = async (kat) => {
    setSelectedKat(kat);
    setShowModal(true);
    setLoadingKomoditas(true);
    const data = await getKomoditas(kat.kategori);
    setKomoditasList(data);
    setLoadingKomoditas(false);
  };

  const addToKeranjang = (item) => {
    setKeranjang((prev) => {
      const exist = prev.find((i) => i.id === item.id);
      if (exist) return prev.map((i) => i.id === item.id ? { ...i, qty: i.qty + 1 } : i);
      return [...prev, { ...item, qty: 1 }];
    });
    showToastMsg(`${item.nama} ditambahkan`);
  };

  const changeQty = (id, delta) => {
    setKeranjang((prev) => {
      const updated = prev.map((i) => i.id === id ? { ...i, qty: i.qty + delta } : i);
      return updated.filter((i) => i.qty > 0);
    });
  };

  const removeItem = (id) => setKeranjang((prev) => prev.filter((i) => i.id !== id));

  const handleBudgetChange = (e) => {
    const raw = e.target.value.replace(/\D/g, "");
    setBudgetDisplay(raw);
    setBudget(raw ? parseInt(raw) : 0);
  };

  const handlePredict = async () => {
    if (!keranjang.length) return showToastMsg("Keranjang masih kosong");
    if (!budget) return showToastMsg("Masukkan budget terlebih dahulu", "warning");
    setLoadingPredict(true);
    try {
      const payload = keranjang.map((i) => ({ komoditas_id: i.id, jumlah: i.qty }));
      const result  = await predictBelanja(budget, payload);
      setHasilPredict(result);
    } catch {
      setPredictError(true);
      showToastMsg("Gagal menghubungi API", "error");
    }
    setLoadingPredict(false);
  };

  const showToastMsg = (msg, type = "success") => {
    setToast({ msg, type });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast({ msg: "", type: "info" }), 3000);
  };

  const liveTotal = useMemo(() =>
    keranjang.reduce((s, i) => s + (i.harga_ref || 0) * i.qty, 0),
    [keranjang]
  );

  // Kalkulasi lokal kalau belum ada hasil predict
  const totalPrediksi = useMemo(() => {
    const fromPredict = hasilPredict?.total_prediksi;
    if (fromPredict != null && !isNaN(fromPredict) && keranjang.length > 0) return fromPredict;
    return liveTotal;
  }, [keranjang, hasilPredict, liveTotal]);

  useEffect(() => {
    setHasilPredict(null);
    setPredictError(false);
  }, [keranjang]);

  const sisaBudget = budget - liveTotal;
  const persen     = budget > 0 ? Math.min(100, (liveTotal / budget) * 100) : 0;
  const status     = persen < 80 ? "aman" : persen < 100 ? "perhatian" : "over_budget";

  const statusInfo = {
    aman:       { icon: "✅", title: "Status: Budget Aman",     desc: "Belanja Anda masih dalam budget" },
    perhatian:  { icon: "⚠️", title: "Status: Hampir Habis",    desc: "Budget Anda hampir terpakai semua" },
    over_budget:{ icon: "❌", title: "Status: Melebihi Budget", desc: "Total belanja melebihi budget" },
  }[status];

  const substitutions = hasilPredict?.smart_substitution || [];
  const totalHemat    = hasilPredict?.potensi_hemat_total || 0;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');

        .db-root { font-family: 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif; }

        @keyframes db-pulse-dot {
          0%,100% { opacity:1; transform:scale(1); }
          50%      { opacity:.5; transform:scale(.85); }
        }
        @keyframes db-toast-in {
          from { opacity:0; transform:translateX(20px) scale(.96); }
          to   { opacity:1; transform:none; }
        }

        .db-pulse-dot { animation: db-pulse-dot 1.2s ease-in-out infinite; }
        .db-toast     { animation: db-toast-in .28s cubic-bezier(.34,1.56,.64,1) forwards; }

        .db-stat-card {
          background: white; border-radius: 18px;
          border: 1.5px solid #e8f5e9; padding: 20px 20px 22px;
          position: relative; overflow: hidden;
          box-shadow: 0 2px 12px rgba(27,67,50,.05);
          transition: all .25s ease;
        }
        .db-stat-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 28px rgba(27,67,50,.1);
          border-color: #a7f3d0;
        }

        .db-kat-card {
          border-radius: 14px; padding: 14px 8px 12px;
          display: flex; flex-direction: column;
          align-items: center; gap: 6px; cursor: pointer;
          background: white; transition: all .2s ease;
          border: 1.5px solid #e8f5e9;
          box-shadow: 0 1px 6px rgba(27,67,50,.04);
        }
        .db-kat-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 20px rgba(27,67,50,.1);
          border-color: #a7f3d0;
        }
        .db-kat-card.active { border-color: #1B4332; background: #f0fdf4; }

        .db-item-row {
          display: flex; align-items: center;
          justify-content: space-between;
          padding: 12px 16px; border-radius: 12px;
          border: 1.5px solid #e8f5e9; cursor: pointer;
          transition: all .15s;
        }
        .db-item-row:hover { background: #f0fdf4; border-color: #a7f3d0; }

        .db-qty-btn {
          width: 26px; height: 26px; border-radius: 8px;
          border: 1.5px solid #e8f5e9; background: white;
          cursor: pointer; display: flex; align-items: center;
          justify-content: center; transition: all .15s;
          color: #1B4332;
        }
        .db-qty-btn:hover { background: #f0fdf4; border-color: #1B4332; }

        .db-predict-btn {
          width: 100%; padding: 13px;
          background: linear-gradient(135deg, #1B4332, #2d6a4f);
          color: white; border: none; border-radius: 14px;
          font-size: 14px; font-weight: 700; cursor: pointer;
          display: flex; align-items: center; justify-content: center;
          gap: 8px; font-family: inherit;
          box-shadow: 0 4px 16px rgba(27,67,50,.25);
          transition: all .2s ease;
        }
        .db-predict-btn:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(27,67,50,.35);
        }
        .db-predict-btn:disabled { opacity: .65; cursor: not-allowed; }

        .db-budget-input {
          width: 100%; border: 1.5px solid #e8f5e9;
          border-radius: 12px; padding: 13px 14px 13px 46px;
          font-family: 'DM Mono', monospace; font-size: 15px;
          font-weight: 500; color: #1a1a1a;
          background: #f8fdf9; outline: none;
          transition: border-color .18s, box-shadow .18s;
        }
        .db-budget-input:focus {
          border-color: #1B4332;
          box-shadow: 0 0 0 3px rgba(27,67,50,.08);
          background: white;
        }
      `}</style>

      <div className="db-root" style={{
        display: "grid", gridTemplateColumns: "1fr 390px",
        gap: 24, alignItems: "start",
      }}>

        {/* ════════════════ KIRI ════════════════ */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

          {/* ── STAT CARDS ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
            <StatCard
              label="Sisa Budget"
              value={formatRp(sisaBudget)}
              valueColor={sisaBudget >= 0 ? "#1B4332" : "#dc2626"}
              badge={sisaBudget >= 0 ? "✓ Aman" : "⚠ Perhatikan"}
              badgeColor={sisaBudget >= 0 ? { bg:"#f0fdf4", text:"#1B4332", border:"#a7f3d0" }
                                         : { bg:"#fef2f2", text:"#dc2626", border:"#fecaca" }}
              accent="#e6faf5"
              barColor={sisaBudget >= 0
                ? "linear-gradient(90deg,#1B4332,#2d6a4f)"
                : "linear-gradient(90deg,#dc2626,#ef4444)"}
            />
            <StatCard
              label="Total Prediksi"
              value={formatRp(totalPrediksi)}
              valueColor="#b45309"
              badge={`${keranjang.length} item`}
              badgeColor={{ bg:"#fffbeb", text:"#b45309", border:"#fde68a" }}
              accent="#fff5f1"
              barColor="linear-gradient(90deg,#F9A825,#f59f00)"
            />
            <StatCard
              label="Potensi Hemat"
              value={formatRp(totalHemat)}
              valueColor="#1d4ed8"
              badge="Smart Sub"
              badgeColor={{ bg:"#eff6ff", text:"#1d4ed8", border:"#bfdbfe" }}
              accent="#eff6ff"
              barColor="linear-gradient(90deg,#3b82f6,#06b6d4)"
            />
          </div>

          {/* ── BUDGET INPUT ── */}
          <div style={card}>
            <div style={cardHeader}>
              <div style={{ width:34, height:34, borderRadius:10, background:"#f0fdf4",
                display:"flex", alignItems:"center", justifyContent:"center" }}>
                <Wallet size={17} color="#1B4332" />
              </div>
              <div>
                <div style={{ fontSize:15, fontWeight:800, color:"#1B4332" }}>Budget Belanja</div>
                <div style={{ fontSize:11.5, color:"#9ca3af", marginTop:1 }}>
                  Masukkan anggaran belanja Anda
                </div>
              </div>
            </div>
            <div style={{ padding:"18px 20px" }}>
              <label style={{ fontSize:13, color:"#6b7280", fontWeight:600,
                display:"block", marginBottom:8 }}>
                Masukkan Total Budget (Rp)
              </label>
              <div style={{ position:"relative", marginBottom:6 }}>
                <span style={{ position:"absolute", left:16, top:"50%", transform:"translateY(-50%)",
                  fontSize:13, fontWeight:700, color:"#1B4332" }}>Rp</span>
                <input
                  className="db-budget-input"
                  type="text"
                  value={budgetDisplay}
                  onChange={handleBudgetChange}
                  placeholder="Contoh: 500000"
                />
              </div>
              <p style={{ fontSize:12, color:"#9ca3af" }}>
                Masukkan angka tanpa titik atau koma
              </p>
            </div>
          </div>

          {/* ── KATEGORI BAHAN POKOK ── */}
          <div style={card}>
            <div style={cardHeader}>
              <div style={{ width:34, height:34, borderRadius:10, background:"#fff7ed",
                display:"flex", alignItems:"center", justifyContent:"center" }}>
                <ShoppingCart size={17} color="#f97316" />
              </div>
              <div>
                <div style={{ fontSize:15, fontWeight:800, color:"#1B4332" }}>
                  Kategori Bahan Pokok
                </div>
                <div style={{ fontSize:11.5, color:"#9ca3af", marginTop:1 }}>
                  Pilih kategori untuk menambahkan ke keranjang
                </div>
              </div>
            </div>
            <div style={{ padding:"16px 20px" }}>
              {kategoriError ? (
                <ErrorCard type="network" compact
                  onRetry={async () => {
                    setKategoriError(false);
                    try { setKategoriList(await getKategori()); }
                    catch { setKategoriError(true); }
                  }}
                />
              ) : kategoriList.length === 0 ? (
                <div style={{ display:"flex", alignItems:"center", gap:10,
                  color:"#9ca3af", fontSize:14, padding:"8px 0" }}>
                  <span className="db-pulse-dot" style={{ width:8, height:8, borderRadius:"50%",
                    background:"#1B4332", display:"inline-block" }} />
                  Memuat kategori...
                </div>
              ) : (
                /* 4 KOLOM — lebih kompak */
                <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:10 }}>
                  {kategoriList.map((k) => {
                    const meta = KATEGORI_ICON[k.kategori] || { icon:Package, bg:"#f1f5f9", color:"#475569" };
                    const Icon = meta.icon;
                    return (
                      <div key={k.kategori}
                        className={`db-kat-card${selectedKat?.kategori === k.kategori ? " active" : ""}`}
                        onClick={() => openKategori(k)}>
                        <div style={{ width:44, height:44, borderRadius:12,
                          background:meta.bg, display:"flex", alignItems:"center",
                          justifyContent:"center", flexShrink:0 }}>
                          {ICON_CATALOG[k.kategori]
                            ? <img src={ICON_CATALOG[k.kategori]}
                                style={{ width:26, height:26, objectFit:"contain" }}
                                alt={k.kategori} />
                            : <Icon size={22} color={meta.color} />
                          }
                        </div>
                        <span style={{ fontSize:11, fontWeight:700, textAlign:"center",
                          color:"#374151", lineHeight:1.3 }}>
                          {k.kategori}
                        </span>
                        <span style={{ fontSize:10.5, color:"#9ca3af", fontWeight:500 }}>
                          {k.jumlah_komoditas} item
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ════════════════ KANAN ════════════════ */}
        <div style={{ display:"flex", flexDirection:"column", gap:20 }}>

          {/* ── KERANJANG ── */}
          <div style={card}>
            {/* Header */}
            <div style={{ ...cardHeader, justifyContent:"space-between" }}>
              <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                <div style={{ width:34, height:34, borderRadius:10, background:"#eff6ff",
                  display:"flex", alignItems:"center", justifyContent:"center" }}>
                  <ShoppingCart size={17} color="#3b82f6" />
                </div>
                <div>
                  <div style={{ fontSize:15, fontWeight:800, color:"#1B4332" }}>
                    Keranjang Belanja
                  </div>
                  {keranjang.length > 0 && (
                    <div style={{ fontSize:11.5, color:"#9ca3af", marginTop:1 }}>
                      {keranjang.length} komoditas dipilih
                    </div>
                  )}
                </div>
              </div>
              {keranjang.length > 0 && (
                <span style={{ background:"#1B4332", color:"white", fontSize:11,
                  fontWeight:800, padding:"3px 10px", borderRadius:20 }}>
                  {keranjang.length}
                </span>
              )}
            </div>

            {/* Empty state */}
            {keranjang.length === 0 ? (
              <div style={{ textAlign:"center", padding:"36px 20px", color:"#9ca3af",
                fontSize:14, display:"flex", flexDirection:"column", alignItems:"center" }}>
                <div style={{ width:56, height:56, borderRadius:16, background:"#f8fdf9",
                  border:"1.5px solid #e8f5e9", display:"flex", alignItems:"center",
                  justifyContent:"center", marginBottom:12 }}>
                  <ShoppingCart size={24} color="#d1fae5" />
                </div>
                <div style={{ fontWeight:700, color:"#374151", marginBottom:4 }}>
                  Keranjang masih kosong
                </div>
                <div style={{ fontSize:12.5 }}>Pilih kategori untuk menambahkan</div>
              </div>
            ) : (
              <div style={{ padding:"12px 16px", display:"flex", flexDirection:"column", gap:8 }}>
                {keranjang.map((item) => (
                  <div key={item.id} style={{
                    display:"flex", flexDirection:"column", gap:10,
                    padding:"12px 14px", background:"#f8fdf9", borderRadius:12,
                    border:"1.5px solid #e8f5e9",
                  }}>
                    {/* Baris atas: nama + harga satuan */}
                    <div>
                      <div style={{ fontSize:14.5, fontWeight:700, color:"#1a1a1a", marginBottom:3 }}>
                        {item.nama}
                      </div>
                      <div style={{ fontSize:12.5, color:"#9ca3af", fontFamily:"DM Mono,monospace" }}>
                        {formatRp(item.harga_ref)} / {item.satuan}
                      </div>
                    </div>
                    {/* Baris bawah: qty controls + total + hapus */}
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <button className="db-qty-btn" onClick={() => changeQty(item.id, -1)}>
                        <Minus size={11} />
                      </button>
                      <span style={{ fontSize:14, fontWeight:800, minWidth:22,
                        textAlign:"center", color:"#1B4332" }}>
                        {item.qty}
                      </span>
                      <button className="db-qty-btn" onClick={() => changeQty(item.id, 1)}>
                        <Plus size={11} />
                      </button>
                      <span style={{ fontSize:13, fontWeight:700, fontFamily:"DM Mono,monospace",
                        color:"#374151", marginLeft:"auto" }}>
                        {formatRp(item.harga_ref * item.qty)}
                      </span>
                      <button onClick={() => removeItem(item.id)}
                        style={{ background:"none", border:"none", cursor:"pointer",
                          color:"#9ca3af", padding:4, display:"flex", alignItems:"center",
                          transition:"color .15s" }}
                        onMouseEnter={e=>e.currentTarget.style.color="#dc2626"}
                        onMouseLeave={e=>e.currentTarget.style.color="#9ca3af"}>
                        <X size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* PROGRESS BAR */}
            {budget > 0 && (
              <div style={{ margin:"0 18px 16px" }}>
                <div style={{ display:"flex", justifyContent:"space-between",
                  fontSize:12, color:"#9ca3af", marginBottom:7, fontWeight:500 }}>
                  <span>Penggunaan Budget</span>
                  <span style={{ fontWeight:700, color: status==="aman"?"#1B4332":status==="perhatian"?"#b45309":"#dc2626" }}>
                    {Math.round(persen)}%
                  </span>
                </div>
                <div style={{ height:8, background:"#f0fdf4", borderRadius:20, overflow:"hidden",
                  border:"1px solid #e8f5e9" }}>
                  <div style={{
                    height:"100%", borderRadius:20,
                    width:`${persen}%`,
                    background: status==="aman"
                      ? "linear-gradient(90deg,#1B4332,#2d6a4f)"
                      : status==="perhatian"
                        ? "linear-gradient(90deg,#F9A825,#f59f00)"
                        : "linear-gradient(90deg,#dc2626,#ef4444)",
                    transition:"width 0.4s ease",
                  }} />
                </div>
              </div>
            )}

            {/* SUMMARY */}
            <div style={{ padding:"14px 18px", borderTop:"1px solid #f0fdf4",
              display:"flex", flexDirection:"column", gap:8 }}>
              {[
                { label:"Total Budget",        value:formatRp(budget) },
                { label:"Total Prediksi Harga",value:formatRp(totalPrediksi) },
              ].map((row) => (
                <div key={row.label} style={{ display:"flex", justifyContent:"space-between",
                  fontSize:13.5 }}>
                  <span style={{ color:"#9ca3af" }}>{row.label}</span>
                  <span style={{ fontFamily:"DM Mono,monospace", fontWeight:700,
                    color:"#374151" }}>{row.value}</span>
                </div>
              ))}
              <hr style={{ border:"none", borderTop:"1px solid #f0fdf4", margin:"4px 0" }} />
              <div style={{ display:"flex", justifyContent:"space-between", fontSize:13.5 }}>
                <span style={{ fontWeight:700, color:"#1a1a1a" }}>Sisa Budget</span>
                <span style={{ fontFamily:"DM Mono,monospace", fontWeight:800, fontSize:15,
                  color: sisaBudget >= 0 ? "#1B4332" : "#dc2626" }}>
                  {formatRp(sisaBudget)}
                </span>
              </div>
            </div>

            {/* STATUS */}
            {budget > 0 && keranjang.length > 0 && (
              <div style={{
                margin:"0 16px 16px", padding:"12px 16px",
                borderRadius:14, display:"flex", alignItems:"flex-start", gap:12,
                background: status==="aman"?"#f0fdf4":status==="perhatian"?"#fffbeb":"#fef2f2",
                border:`1.5px solid ${status==="aman"?"#a7f3d0":status==="perhatian"?"#fde68a":"#fecaca"}`,
              }}>
                <span style={{ fontSize:20, flexShrink:0 }}>{statusInfo.icon}</span>
                <div>
                  <div style={{ fontSize:13.5, fontWeight:800,
                    color: status==="aman"?"#1B4332":status==="perhatian"?"#b45309":"#dc2626" }}>
                    {statusInfo.title}
                  </div>
                  <div style={{ fontSize:12, color:"#9ca3af", marginTop:2 }}>{statusInfo.desc}</div>
                </div>
              </div>
            )}

            {/* TOMBOL PREDIKSI */}
            {keranjang.length > 0 && (
              <div style={{ padding:"0 16px 16px" }}>
                <button className="db-predict-btn" onClick={handlePredict} disabled={loadingPredict}>
                  <ChevronRight size={16} />
                  {loadingPredict ? "Menghitung..." : "Hitung Prediksi"}
                </button>
              </div>
            )}
          </div>

          {/* LOADING PREDIKSI */}
          {loadingPredict && keranjang.length > 0 && <PredictLoading />}

          {/* ERROR PREDIKSI */}
          {predictError && !loadingPredict && keranjang.length > 0 && (
            <ErrorCard type="predict"
              onRetry={async () => { setPredictError(false); await handlePredict(); }} />
          )}

          {/* HASIL PREDIKSI */}
          {hasilPredict && !loadingPredict && keranjang.length > 0 && (
            <SmartSubstitution
              status={status} keranjang={keranjang}
              substitutions={substitutions} totalHemat={totalHemat}
              totalPrediksi={totalPrediksi} budget={budget}
              hasilPredict={hasilPredict} onRemoveItem={removeItem}
            />
          )}
        </div>

        {/* ════════════════ MODAL ════════════════ */}
        {showModal && (
          <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.4)", zIndex:200,
            display:"flex", alignItems:"center", justifyContent:"center",
            backdropFilter:"blur(6px)" }}
            onClick={() => setShowModal(false)}>
            <div style={{ background:"white", borderRadius:22,
              boxShadow:"0 24px 70px rgba(0,0,0,.18)", width:440, maxHeight:"80vh",
              display:"flex", flexDirection:"column", overflow:"hidden" }}
              onClick={(e) => e.stopPropagation()}>

              {/* Modal header */}
              <div style={{ padding:"20px 22px", borderBottom:"1px solid #f0fdf4",
                display:"flex", alignItems:"center", justifyContent:"space-between",
                background:"linear-gradient(135deg,#1B4332,#2d6a4f)" }}>
                <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                  {KATEGORI_ICON[selectedKat?.kategori] && (() => {
                    const meta = KATEGORI_ICON[selectedKat.kategori];
                    const Icon = meta.icon;
                    return (
                      <div style={{ width:34, height:34, borderRadius:10, background:"rgba(255,255,255,.15)",
                        display:"flex", alignItems:"center", justifyContent:"center" }}>
                        {ICON_CATALOG[selectedKat.kategori]
                          ? <img src={ICON_CATALOG[selectedKat.kategori]}
                              style={{ width:20, height:20, objectFit:"contain" }} alt="" />
                          : <Icon size={18} color="white" />
                        }
                      </div>
                    );
                  })()}
                  <div>
                    <div style={{ fontSize:15, fontWeight:800, color:"white" }}>
                      {selectedKat?.kategori}
                    </div>
                    <div style={{ fontSize:11.5, color:"rgba(255,255,255,.6)" }}>
                      Pilih komoditas untuk ditambahkan
                    </div>
                  </div>
                </div>
                <button onClick={() => setShowModal(false)} style={{ width:32, height:32,
                  border:"none", background:"rgba(255,255,255,.15)", borderRadius:10,
                  cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center",
                  color:"white", transition:"background .15s" }}
                  onMouseEnter={e=>e.currentTarget.style.background="rgba(255,255,255,.25)"}
                  onMouseLeave={e=>e.currentTarget.style.background="rgba(255,255,255,.15)"}>
                  <X size={15} />
                </button>
              </div>

              {/* Modal body */}
              <div style={{ padding:16, overflowY:"auto", maxHeight:"60vh" }}>
                {loadingKomoditas ? (
                  <div style={{ textAlign:"center", padding:"32px 0", color:"#9ca3af" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8,
                      justifyContent:"center", fontSize:14 }}>
                      <span className="db-pulse-dot" style={{ width:8, height:8,
                        borderRadius:"50%", background:"#1B4332", display:"inline-block" }} />
                      Memuat komoditas...
                    </div>
                  </div>
                ) : (
                  <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                    {komoditasList.map((item) => (
                      <div key={item.id} className="db-item-row" onClick={() => addToKeranjang(item)}>
                        <div>
                          <div style={{ fontSize:14, fontWeight:700, color:"#1a1a1a" }}>
                            {item.nama}
                          </div>
                          <div style={{ fontSize:12, color:"#9ca3af",
                            fontFamily:"DM Mono,monospace", marginTop:2 }}>
                            {formatRp(item.harga_ref)}/{item.satuan}
                          </div>
                        </div>
                        <button style={{ background:"#1B4332", color:"white", border:"none",
                          width:32, height:32, borderRadius:10, cursor:"pointer",
                          display:"flex", alignItems:"center", justifyContent:"center",
                          boxShadow:"0 2px 8px rgba(27,67,50,.25)", transition:"all .15s" }}
                          onMouseEnter={e=>e.currentTarget.style.background="#2d6a4f"}
                          onMouseLeave={e=>e.currentTarget.style.background="#1B4332"}>
                          <Plus size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TOAST */}
        {toast.msg && <AppToast msg={toast.msg} type={toast.type} />}
      </div>
    </>
  );
}

// ── StatCard ────────────────────────────────────────────────────────

function StatCard({ label, value, valueColor, badge, badgeColor, accent, barColor }) {
  return (
    <div className="db-stat-card">
      {/* Accent blob */}
      <div style={{ position:"absolute", top:-10, right:-10, width:70, height:70,
        borderRadius:"50%", background:accent, opacity:.45, pointerEvents:"none" }} />
      <div style={{ fontSize:11, color:"#9ca3af", fontWeight:700, textTransform:"uppercase",
        letterSpacing:"1px", marginBottom:10 }}>{label}</div>
      <div style={{ fontSize:22, fontWeight:900, letterSpacing:"-.5px",
        color:valueColor, marginBottom:8 }}>{value}</div>
      <span style={{ fontSize:11, fontWeight:700, padding:"3px 10px", borderRadius:20,
        background:badgeColor.bg, color:badgeColor.text,
        border:`1px solid ${badgeColor.border}` }}>
        {badge}
      </span>
      {/* Accent bar */}
      <div style={{ position:"absolute", bottom:0, left:0, right:0, height:3,
        background:barColor, borderRadius:"0 0 18px 18px" }} />
    </div>
  );
}

// ── AppToast ────────────────────────────────────────────────────────

function AppToast({ msg, type }) {
  const cfg = {
    success: { bg:"#f0fdf4", border:"#a7f3d0", color:"#1B4332",   icon:"✅", title:"Berhasil"  },
    warning: { bg:"#fffbeb", border:"#fde68a", color:"#92400e",   icon:"⚠️", title:"Perhatian"  },
    error:   { bg:"#fef2f2", border:"#fecaca", color:"#dc2626",   icon:"❌", title:"Gagal"      },
    info:    { bg:"#eff6ff", border:"#bfdbfe", color:"#1d4ed8",   icon:"ℹ️", title:"Info"       },
  }[type] || {};

  return (
    <div className="db-toast" style={{
      position:"fixed", bottom:28, right:28, zIndex:999,
      display:"flex", alignItems:"flex-start", gap:12,
      background:cfg.bg, border:`1.5px solid ${cfg.border}`,
      borderLeft:`4px solid ${cfg.border}`, borderRadius:14,
      padding:"14px 18px",
      boxShadow:"0 8px 24px rgba(0,0,0,.12), 0 2px 8px rgba(0,0,0,.06)",
      maxWidth:320, minWidth:240,
    }}>
      <span style={{ fontSize:18, lineHeight:1.2, flexShrink:0 }}>{cfg.icon}</span>
      <div>
        <div style={{ fontSize:13.5, fontWeight:800, color:cfg.color, marginBottom:2 }}>
          {cfg.title}
        </div>
        <div style={{ fontSize:12.5, color:cfg.color, opacity:.8, lineHeight:1.5 }}>{msg}</div>
      </div>
    </div>
  );
}

// ── Shared styles ───────────────────────────────────────────────────

const card = {
  background:"white", borderRadius:18,
  border:"1.5px solid #e8f5e9",
  boxShadow:"0 2px 12px rgba(27,67,50,.05)",
  overflow:"hidden",
};
const cardHeader = {
  padding:"18px 20px 16px",
  display:"flex", alignItems:"center", gap:12,
  borderBottom:"1px solid #f0fdf4",
};
