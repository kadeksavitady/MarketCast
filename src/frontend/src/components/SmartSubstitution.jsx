import { Lightbulb, AlertTriangle, XCircle, CheckCircle, Trash2, MinusCircle } from "lucide-react";

function formatRp(val) {
  if (!val && val !== 0) return "Rp 0";
  return "Rp " + Math.round(val).toLocaleString("id-ID");
}

function getSaranKurangi(hasilPredict, budget) {
  if (!hasilPredict?.detail_keranjang?.length) return null;
  const selisih = hasilPredict.total_prediksi - budget;
  if (selisih <= 0) return null;

  const termahal = [...hasilPredict.detail_keranjang]
    .sort((a, b) => b.subtotal - a.subtotal)[0];

  const qtyKurang = Math.ceil(selisih / termahal.harga_per_satuan);
  const qtyBaru   = Math.max(0, termahal.jumlah - qtyKurang);
  const hemat     = qtyKurang * termahal.harga_per_satuan;

  return { item: termahal, qtyKurang, qtyBaru, hemat };
}

function SubItem({ sub }) {
  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-sm)",
      overflow: "hidden",
      marginBottom: 8,
    }}>
      <div style={{ padding: "12px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <span style={badge("#FF6B35")}>Sekarang</span>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{sub.current_nama}</span>
        </div>
        <div style={{ fontSize: 12, fontFamily: "DM Mono,monospace", color: "var(--accent)", fontWeight: 600, marginBottom: 8 }}>
          {formatRp(sub.current_harga)}/kg
        </div>
        <div style={{ textAlign: "center", color: "var(--primary)", fontSize: 18, lineHeight: 1, marginBottom: 8 }}>↓</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <span style={badge("var(--primary)")}>Alternatif</span>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{sub.substitute_nama}</span>
        </div>
        <div style={{ fontSize: 12, fontFamily: "DM Mono,monospace", color: "var(--primary-dark)", fontWeight: 600 }}>
          {formatRp(sub.substitute_harga)}/kg
        </div>
      </div>
      <div style={{
        display: "flex", justifyContent: "space-between",
        padding: "8px 14px",
        background: "var(--primary-light)",
        borderTop: "1px solid #a7f3d0",
      }}>
        <span style={{ fontSize: 12, color: "var(--text-sub)" }}>Potensi hemat</span>
        <span style={{ fontSize: 12.5, fontFamily: "DM Mono,monospace", fontWeight: 800, color: "var(--primary-dark)" }}>
          ↘ {formatRp(sub.potensi_hemat)}
        </span>
      </div>
    </div>
  );
}

export default function SmartSubstitution({
  status, keranjang, substitutions,
  totalHemat, totalPrediksi, budget,
  hasilPredict, onRemoveItem,
}) {
  const saran = getSaranKurangi(hasilPredict, budget);
  const totalSetelahSub = totalPrediksi - totalHemat;
  const masihOver = totalSetelahSub > budget;

  // Skenario A — budget aman
  if (status === "aman") {
    return (
      <div style={{
        ...card,
        border: "1px solid #a7f3d0",
        background: "var(--primary-light)",
        padding: "16px 18px",
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <div style={iconWrap("#dcfce7", "var(--primary-dark)")}>
          <CheckCircle size={18} />
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--primary-dark)" }}>
            Budget Anda Masih Mencukupi
          </div>
          <div style={{ fontSize: 12.5, color: "var(--primary-dark)", opacity: 0.8, marginTop: 2 }}>
            Tidak ada tindakan yang diperlukan. Belanja Anda hemat!
          </div>
        </div>
      </div>
    );
  }

  // Skenario B — perhatian + ada substitusi
  if (status === "perhatian" && substitutions.length > 0) {
    return (
      <div style={card}>
        <div style={{
          padding: "14px 16px", background: "#FEF9C3",
          borderBottom: "1px solid #FDE68A",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <div style={iconWrap("#FEF08A", "#92400E")}>
            <Lightbulb size={16} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: "#92400E" }}>
              Budget Hampir Habis — Ada Alternatif Lebih Hemat
            </div>
            <div style={{ fontSize: 12, color: "#A16207", marginTop: 2 }}>
              Dengan substitusi, Anda bisa hemat {formatRp(totalHemat)}
            </div>
          </div>
          <div style={{ background: "#FDE68A", color: "#92400E", fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 20 }}>
            {substitutions.length} saran
          </div>
        </div>
        <div style={{ padding: "12px 14px" }}>
          {substitutions.map((sub, i) => <SubItem key={i} sub={sub} />)}
        </div>
        <div style={{
          margin: "0 14px 14px",
          background: "linear-gradient(135deg, var(--primary-dark), var(--primary))",
          borderRadius: "var(--radius-sm)", padding: "12px 16px",
          display: "flex", justifyContent: "space-between", alignItems: "center", color: "white",
        }}>
          <span style={{ fontSize: 13, fontWeight: 600, opacity: 0.9 }}>Total Potensi Penghematan</span>
          <span style={{ fontSize: 17, fontWeight: 800, fontFamily: "DM Mono,monospace" }}>{formatRp(totalHemat)}</span>
        </div>
      </div>
    );
  }

  // Skenario C — over budget + ada substitusi
  if (status === "over_budget" && substitutions.length > 0) {
    return (
      <div style={card}>
        <div style={{
          padding: "14px 16px", background: "#FEF2F2",
          borderBottom: "1px solid #FECACA",
          display: "flex", alignItems: "flex-start", gap: 10,
        }}>
          <div style={iconWrap("#FEE2E2", "#DC2626")}>
            <AlertTriangle size={16} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: "#DC2626" }}>
              Budget Melebihi Batas — Perlu Tindakan
            </div>
            <div style={{ fontSize: 12, color: "#991B1B", marginTop: 2 }}>
              Terapkan substitusi berikut untuk menghemat {formatRp(totalHemat)}
            </div>
          </div>
        </div>
        <div style={{ padding: "12px 14px" }}>
          {substitutions.map((sub, i) => <SubItem key={i} sub={sub} />)}
        </div>
        {masihOver && saran && (
          <div style={{
            margin: "0 14px 10px", background: "#FFF7ED",
            border: "1px solid #FED7AA", borderRadius: "var(--radius-sm)", padding: "12px 14px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <MinusCircle size={16} color="#EA580C" />
              <span style={{ fontSize: 13, fontWeight: 700, color: "#EA580C" }}>
                Masih Over Budget — Perlu Kurangi Jumlah
              </span>
            </div>
            <div style={{ fontSize: 12.5, color: "#9A3412", lineHeight: 1.6 }}>
              Setelah substitusi, total masih <strong>{formatRp(totalSetelahSub - budget)}</strong> di atas budget.
              Kurangi <strong>{saran.item.nama}</strong> sebanyak{" "}
              <strong>{saran.qtyKurang} kg</strong> (dari {saran.item.jumlah} kg → {saran.qtyBaru} kg)
              untuk hemat <strong>{formatRp(saran.hemat)}</strong>.
            </div>
          </div>
        )}
        <div style={{
          margin: "0 14px 14px",
          background: "linear-gradient(135deg, var(--primary-dark), var(--primary))",
          borderRadius: "var(--radius-sm)", padding: "12px 16px",
          display: "flex", justifyContent: "space-between", alignItems: "center", color: "white",
        }}>
          <span style={{ fontSize: 13, fontWeight: 600, opacity: 0.9 }}>Total Potensi Penghematan</span>
          <span style={{ fontSize: 17, fontWeight: 800, fontFamily: "DM Mono,monospace" }}>{formatRp(totalHemat)}</span>
        </div>
      </div>
    );
  }

  // Skenario D — over budget + tidak ada substitusi
  if (status === "over_budget" && substitutions.length === 0) {
    const termahal = hasilPredict?.detail_keranjang?.length
      ? [...hasilPredict.detail_keranjang].sort((a, b) => b.subtotal - a.subtotal)[0]
      : null;

    return (
      <div style={card}>
        <div style={{
          padding: "14px 16px", background: "#FEF2F2",
          borderBottom: "1px solid #FECACA",
          display: "flex", alignItems: "flex-start", gap: 10,
        }}>
          <div style={iconWrap("#FEE2E2", "#DC2626")}>
            <XCircle size={16} />
          </div>
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: "#DC2626" }}>Budget Tidak Mencukupi</div>
            <div style={{ fontSize: 12, color: "#991B1B", marginTop: 2 }}>
              Tidak ada alternatif substitusi yang tersedia
            </div>
          </div>
        </div>
        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            background: "#F3F4F6", border: "1px solid #E5E7EB",
            borderRadius: "var(--radius-sm)", padding: "10px 14px",
          }}>
            <XCircle size={14} color="#9CA3AF" />
            <span style={{ fontSize: 12.5, color: "#6B7280" }}>
              Tidak ada substitusi untuk komoditas ini
            </span>
          </div>
          {termahal && (
            <div style={{
              background: "#FEF2F2", border: "1px solid #FECACA",
              borderRadius: "var(--radius-sm)", padding: "12px 14px",
            }}>
              <div style={{ fontSize: 11, color: "#DC2626", fontWeight: 700, marginBottom: 6, letterSpacing: "0.5px" }}>
                ITEM PALING MEMBEBANI BUDGET
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 700 }}>{termahal.nama}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "DM Mono,monospace" }}>
                    {termahal.jumlah} kg × {formatRp(termahal.harga_per_satuan)} = {formatRp(termahal.subtotal)}
                  </div>
                </div>
                <button
                  onClick={() => onRemoveItem(termahal.komoditas_id)}
                  style={{
                    display: "flex", alignItems: "center", gap: 4,
                    background: "#DC2626", color: "white",
                    border: "none", borderRadius: 8,
                    padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  <Trash2 size={12} />
                  Hapus
                </button>
              </div>
            </div>
          )}
          {saran && (
            <div style={{
              background: "#FFF7ED", border: "1px solid #FED7AA",
              borderRadius: "var(--radius-sm)", padding: "12px 14px",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <MinusCircle size={14} color="#EA580C" />
                <span style={{ fontSize: 12.5, fontWeight: 700, color: "#EA580C" }}>Saran Pengurangan</span>
              </div>
              <div style={{ fontSize: 12.5, color: "#9A3412", lineHeight: 1.6 }}>
                Kurangi <strong>{saran.item.nama}</strong> dari {saran.item.jumlah} kg menjadi{" "}
                <strong>{saran.qtyBaru} kg</strong> untuk hemat <strong>{formatRp(saran.hemat)}</strong>.
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
}

const card = {
  background: "var(--card-bg)", borderRadius: "var(--radius)",
  border: "1px solid var(--border)", boxShadow: "var(--shadow-sm)", overflow: "hidden",
};

function iconWrap(bg, color) {
  return {
    width: 32, height: 32, borderRadius: 8, background: bg, color: color,
    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
  };
}

function badge(bg) {
  return {
    fontSize: 10, fontWeight: 700, textTransform: "uppercase",
    letterSpacing: "0.5px", padding: "2px 7px", borderRadius: 20,
    color: "white", background: bg, flexShrink: 0,
  };
}