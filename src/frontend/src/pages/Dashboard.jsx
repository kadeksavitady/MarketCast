import { useState, useEffect, useRef, useMemo } from "react";
import { getKomoditas, getKategori, predictBelanja } from "../services/api";
import {
  ShoppingCart, Wallet, Lightbulb, X, Plus, Minus,
  ChevronRight, Package, Beef, Droplets, Egg,
  Leaf, Fish, Wheat, Cookie, FlameKindling
} from "lucide-react";
import SmartSubstitution from "../components/SmartSubstitution";

// Icon mapping per kategori
const KATEGORI_ICON = {
  "BERAS":    { icon: Wheat,         bg: "#fff7ed", color: "#f59e0b" },
  "DAGING":   { icon: Beef,          bg: "#fef2f2", color: "#ef4444" },
  "MINYAK GORENG": { icon: Droplets, bg: "#fefce8", color: "#eab308" },
  "TELUR":    { icon: Egg,           bg: "#fffbeb", color: "#f59e0b" },
  "SAYUR MAYUR": { icon: Leaf,       bg: "#f0fdf4", color: "#22c55e" },
  "IKAN SEGAR":  { icon: Fish,       bg: "#eff6ff", color: "#3b82f6" },
  "CABE":     { icon: FlameKindling, bg: "#fef2f2", color: "#ef4444" },
  "BAWANG":   { icon: Leaf,          bg: "#f5f3ff", color: "#8b5cf6" },
  "GULA":     { icon: Cookie,        bg: "#fdf4ff", color: "#a855f7" },
  "TEPUNG":   { icon: Package,       bg: "#f8fafc", color: "#64748b" },
  "SUSU":     { icon: Package,       bg: "#eff6ff", color: "#3b82f6" },
  "GARAM":    { icon: Package,       bg: "#f8fafc", color: "#94a3b8" },
  "MIE INSTAN": { icon: Package,     bg: "#fff7ed", color: "#f97316" },
  "IKAN ASIN":  { icon: Fish,        bg: "#f0fdf4", color: "#16a34a" },
  "PALAWIJA":   { icon: Wheat,       bg: "#fefce8", color: "#ca8a04" },
  "BARANG PENTING LAINNYA": { icon: Package, bg: "#f1f5f9", color: "#475569" },
};

function formatRp(val) {
  if (!val && val !== 0) return "Rp 0";
  return "Rp " + Math.round(val).toLocaleString("id-ID");
}

export default function Dashboard() {
  const [kategoriList, setKategoriList] = useState([]);
  const [selectedKat, setSelectedKat] = useState(null);
  const [komoditasList, setKomoditasList] = useState([]);
  const [loadingKomoditas, setLoadingKomoditas] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [keranjang, setKeranjang] = useState([]);
  const [budget, setBudget] = useState(500000);
  const [budgetDisplay, setBudgetDisplay] = useState("500000");
  const [hasilPredict, setHasilPredict] = useState(null);
  const [loadingPredict, setLoadingPredict] = useState(false);
  const [toast, setToast] = useState("");
  const toastTimer = useRef(null);

  useEffect(() => {
    getKategori().then(setKategoriList);
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
    if (!budget) return showToastMsg("Masukkan budget dulu");
    setLoadingPredict(true);
    try {
      const payload = keranjang.map((i) => ({
        komoditas_id: i.id,
        jumlah: i.qty,
      }));
      const result = await predictBelanja(budget, payload);
      setHasilPredict(result);
    } catch (e) {
      showToastMsg("Gagal menghubungi API");
    }
    setLoadingPredict(false);
  };

  const showToastMsg = (msg) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 2500);
  };

  // Kalkulasi lokal kalau belum ada hasil predict
  const totalPrediksi = useMemo(() => {
    if (hasilPredict && keranjang.length > 0) return hasilPredict.total_prediksi;
    return keranjang.reduce((s, i) => s + i.harga_ref * i.qty, 0);
  }, [keranjang, hasilPredict]);

  useEffect(() => {
    if (keranjang.length === 0) setHasilPredict(null);
  }, [keranjang]);

  const sisaBudget = budget - totalPrediksi;
  const persen = budget > 0 ? Math.min(100, (totalPrediksi / budget) * 100) : 0;
  const status = persen < 80 ? "safe" : persen < 100 ? "warning" : "danger";

  const statusInfo = {
    safe:    { icon: "✅", title: "Status: Budget Aman", desc: "Belanja Anda masih dalam budget" },
    warning: { icon: "⚠️", title: "Status: Hampir Habis", desc: "Budget Anda hampir terpakai semua" },
    danger:  { icon: "❌", title: "Status: Melebihi Budget", desc: "Total belanja melebihi budget" },
  }[status];

  const substitutions = hasilPredict?.smart_substitution || [];
  const totalHemat = hasilPredict?.potensi_hemat_total || 0;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 24, alignItems: "start" }}>

      {/* ── KIRI ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

        {/* STAT CARDS */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
          <StatCard label="Sisa Budget" value={formatRp(sisaBudget)}
            valueColor={sisaBudget >= 0 ? "var(--primary-dark)" : "var(--red)"}
            badge={sisaBudget >= 0 ? "✓ Aman" : "⚠ Perhatikan"}
            badgeOk={sisaBudget >= 0} accent="#e6faf5" />
          <StatCard label="Total Prediksi" value={formatRp(totalPrediksi)}
            valueColor="var(--accent)" badge={`${keranjang.length} item`}
            badgeOk={false} accent="#fff5f1" />
          <StatCard label="Potensi Hemat" value={formatRp(totalHemat)}
            valueColor="var(--blue)" badge="💡 Smart Sub"
            badgeOk={true} accent="#eff6ff" />
        </div>

        {/* BUDGET INPUT */}
        <div style={card}>
          <CardHeader icon={<Wallet size={16} color="var(--primary-dark)" />}
            bg="var(--primary-light)" title="Budget Belanja" />
          <div style={{ padding: 20 }}>
            <label style={labelStyle}>Masukkan Total Budget (Rp)</label>
            <div style={{ position: "relative", marginBottom: 6 }}>
              <span style={budgetPrefix}>Rp</span>
              <input
                style={budgetField}
                type="text"
                value={budgetDisplay}
                onChange={handleBudgetChange}
                placeholder="Contoh: 500000"
              />
            </div>
            <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Masukkan angka tanpa titik atau koma
            </p>
          </div>
        </div>

        {/* KATEGORI */}
        <div style={card}>
          <CardHeader icon={<ShoppingCart size={16} color="#f97316" />}
            bg="#fff7ed" title="Kategori Bahan Pokok" />
          <div style={{ padding: 20 }}>
            {kategoriList.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
                Memuat kategori...
              </p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
                {kategoriList.map((k) => {
                  const meta = KATEGORI_ICON[k.kategori] || { icon: Package, bg: "#f1f5f9", color: "#475569" };
                  const Icon = meta.icon;
                  return (
                    <div key={k.kategori} onClick={() => openKategori(k)}
                      style={{ ...kategoriCard, border: selectedKat?.kategori === k.kategori ? "1.5px solid var(--primary)" : "1.5px solid var(--border)" }}>
                      <div style={{ ...kategoriIconWrap, background: meta.bg }}>
                        <Icon size={26} color={meta.color} />
                      </div>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{k.kategori}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
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

      {/* ── KANAN ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

        {/* KERANJANG */}
        <div style={card}>
          <div style={{ ...cardHeader, justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ ...iconWrap, background: "#eff6ff" }}>
                <ShoppingCart size={16} color="#3b82f6" />
              </div>
              <span style={cardTitle}>Keranjang Belanja</span>
            </div>
            {keranjang.length > 0 && (
              <span style={badge}>{keranjang.length}</span>
            )}
          </div>

          {keranjang.length === 0 ? (
            <div style={emptyCart}>
              <ShoppingCart size={36} style={{ marginBottom: 8, opacity: 0.3 }} />
              <div>Keranjang masih kosong</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Pilih kategori untuk menambahkan</div>
            </div>
          ) : (
            <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              {keranjang.map((item) => (
                <div key={item.id} style={keranjangItem}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{item.nama}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "DM Mono,monospace" }}>
                      {formatRp(item.harga_ref)}/{item.satuan}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button style={qtyBtn} onClick={() => changeQty(item.id, -1)}><Minus size={12} /></button>
                    <span style={{ fontSize: 13, fontWeight: 700, minWidth: 20, textAlign: "center" }}>{item.qty}</span>
                    <button style={qtyBtn} onClick={() => changeQty(item.id, 1)}><Plus size={12} /></button>
                    <span style={{ fontSize: 12.5, fontWeight: 700, fontFamily: "DM Mono,monospace" }}>
                      {formatRp(item.harga_ref * item.qty)}
                    </span>
                    <button style={delBtn} onClick={() => removeItem(item.id)}><X size={12} /></button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* PROGRESS */}
          {budget > 0 && (
            <div style={{ margin: "0 20px 14px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-sub)", marginBottom: 6 }}>
                <span>Penggunaan Budget</span>
                <span>{Math.round(persen)}%</span>
              </div>
              <div style={{ height: 8, background: "var(--border)", borderRadius: 20, overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 20,
                  width: `${persen}%`,
                  background: status === "safe" ? "var(--primary)" : status === "warning" ? "var(--yellow)" : "var(--red)",
                  transition: "width 0.4s ease"
                }} />
              </div>
            </div>
          )}

          {/* SUMMARY */}
          <div style={{ padding: "16px 18px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              { label: "Total Budget", value: formatRp(budget) },
              { label: "Total Prediksi Harga", value: formatRp(totalPrediksi) },
            ].map((row) => (
              <div key={row.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 13.5 }}>
                <span style={{ color: "var(--text-sub)" }}>{row.label}</span>
                <span style={{ fontFamily: "DM Mono,monospace", fontWeight: 700 }}>{row.value}</span>
              </div>
            ))}
            <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "4px 0" }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13.5 }}>
              <span style={{ fontWeight: 700 }}>Sisa Budget</span>
              <span style={{ fontFamily: "DM Mono,monospace", fontWeight: 700, fontSize: 15, color: "var(--primary-dark)" }}>
                {formatRp(sisaBudget)}
              </span>
            </div>
          </div>

          {/* STATUS */}
          <div style={{
            margin: "0 16px 16px",
            padding: "12px 14px",
            borderRadius: "var(--radius-sm)",
            display: "flex", alignItems: "flex-start", gap: 10,
            background: status === "safe" ? "#e6faf5" : status === "warning" ? "#fff7ed" : "#fef2f2",
            border: `1px solid ${status === "safe" ? "#a7f3d0" : status === "warning" ? "#fed7aa" : "#fecaca"}`,
          }}>
            <span style={{ fontSize: 18 }}>{statusInfo.icon}</span>
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 700 }}>{statusInfo.title}</div>
              <div style={{ fontSize: 12, color: "var(--text-sub)", marginTop: 1 }}>{statusInfo.desc}</div>
            </div>
          </div>

          {/* TOMBOL PREDIKSI */}
          {keranjang.length > 0 && (
            <div style={{ padding: "0 16px 16px" }}>
              <button
                onClick={handlePredict}
                disabled={loadingPredict}
                style={{
                  width: "100%", padding: "12px",
                  background: "linear-gradient(135deg, var(--primary-dark), var(--primary))",
                  color: "white", border: "none", borderRadius: "var(--radius-sm)",
                  fontSize: 14, fontWeight: 700, cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                }}
              >
                <ChevronRight size={16} />
                {loadingPredict ? "Menghitung..." : "Hitung Prediksi"}
              </button>
            </div>
          )}
        </div>

        {/* SMART SUBSTITUTION — semua skenario */}
        {hasilPredict && keranjang.length > 0 && (
          <SmartSubstitution
            status={hasilPredict?.status || status}
            keranjang={keranjang}
            substitutions={substitutions}
            totalHemat={totalHemat}
            totalPrediksi={totalPrediksi}
            budget={budget}
            hasilPredict={hasilPredict}
            onRemoveItem={removeItem}
          />
        )}
      </div>

      {/* MODAL KATEGORI */}
      {showModal && (
        <div style={modalOverlay} onClick={() => setShowModal(false)}>
          <div style={modalBox} onClick={(e) => e.stopPropagation()}>
            <div style={modalHeader}>
              <span style={{ fontSize: 16, fontWeight: 700 }}>{selectedKat?.kategori}</span>
              <button style={modalClose} onClick={() => setShowModal(false)}><X size={14} /></button>
            </div>
            <div style={{ padding: 16, overflowY: "auto", maxHeight: "60vh" }}>
              {loadingKomoditas ? (
                <p style={{ color: "var(--text-muted)", fontSize: 14 }}>Memuat...</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {komoditasList.map((item) => (
                    <div key={item.id} style={itemRow} onClick={() => addToKeranjang(item)}>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{item.nama}</div>
                        <div style={{ fontSize: 12, color: "var(--text-sub)", fontFamily: "DM Mono,monospace" }}>
                          {formatRp(item.harga_ref)}/{item.satuan}
                        </div>
                      </div>
                      <button style={addBtn}><Plus size={14} /></button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TOAST */}
      {toast && (
        <div style={toastStyle}>✅ {toast}</div>
      )}
    </div>
  );
}

// ── Sub-components ──
function StatCard({ label, value, valueColor, badge, badgeOk, accent }) {
  return (
    <div style={{ ...card, padding: 18, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: 0, right: 0, width: 80, height: 80, borderRadius: "50%", background: accent, opacity: 0.5 }} />
      <div style={{ fontSize: 12, color: "var(--text-sub)", fontWeight: 500, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.5px", color: valueColor }}>{value}</div>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11, fontWeight: 600, padding: "2px 7px", borderRadius: 20, marginTop: 6, background: badgeOk ? "#e6faf5" : "#fef2f2", color: badgeOk ? "var(--primary-dark)" : "var(--accent)" }}>
        {badge}
      </div>
    </div>
  );
}

function CardHeader({ icon, bg, title }) {
  return (
    <div style={cardHeader}>
      <div style={{ ...iconWrap, background: bg }}>{icon}</div>
      <span style={cardTitle}>{title}</span>
    </div>
  );
}

// ── Styles ──
const card = { background: "var(--card-bg)", borderRadius: "var(--radius)", border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)", overflow: "hidden" };
const cardHeader = { padding: "18px 20px 14px", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid var(--border)" };
const iconWrap = { width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" };
const cardTitle = { fontSize: 15, fontWeight: 700 };
const labelStyle = { fontSize: 13, color: "var(--text-sub)", fontWeight: 500, display: "block", marginBottom: 8 };
const budgetPrefix = { position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", fontSize: 13, fontWeight: 600, color: "var(--text-sub)" };
const budgetField = { width: "100%", border: "1.5px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "12px 14px 12px 42px", fontFamily: "DM Mono,monospace", fontSize: 15, fontWeight: 500, color: "var(--text-main)", background: "var(--bg)", outline: "none" };
const kategoriCard = { borderRadius: "var(--radius)", padding: "18px 12px 14px", display: "flex", flexDirection: "column", alignItems: "center", gap: 8, cursor: "pointer", background: "white", transition: "all 0.18s" };
const kategoriIconWrap = { width: 52, height: 52, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center" };
const keranjangItem = { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", background: "var(--bg)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", flexWrap: "wrap", gap: 8 };
const qtyBtn = { width: 24, height: 24, borderRadius: 6, border: "1px solid var(--border)", background: "white", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" };
const delBtn = { background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4, display: "flex", alignItems: "center" };
const badge = { background: "var(--primary)", color: "white", fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 20 };
const emptyCart = { textAlign: "center", padding: "32px 20px", color: "var(--text-muted)", fontSize: 14, display: "flex", flexDirection: "column", alignItems: "center" };
const subBadge = { fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", padding: "2px 7px", borderRadius: 20, color: "white" };
const modalOverlay = { position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", backdropFilter: "blur(4px)" };
const modalBox = { background: "white", borderRadius: "var(--radius)", boxShadow: "var(--shadow-lg)", width: 420, maxHeight: "80vh", display: "flex", flexDirection: "column", overflow: "hidden" };
const modalHeader = { padding: "18px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" };
const modalClose = { width: 30, height: 30, border: "none", background: "var(--bg)", borderRadius: 8, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" };
const itemRow = { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", cursor: "pointer" };
const addBtn = { background: "var(--primary)", color: "white", border: "none", width: 28, height: 28, borderRadius: 8, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" };
const toastStyle = { position: "fixed", bottom: 28, right: 28, background: "var(--text-main)", color: "white", padding: "12px 18px", borderRadius: "var(--radius-sm)", fontSize: 13.5, fontWeight: 600, zIndex: 999, display: "flex", alignItems: "center", gap: 8, boxShadow: "var(--shadow-lg)" };