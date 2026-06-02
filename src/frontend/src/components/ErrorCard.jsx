import { useState } from "react";
import { RefreshCw, WifiOff, Server, AlertTriangle, Database } from "lucide-react";

const ERROR_CONFIG = {
  model: {
    Icon: Server,
    iconBg: "#FFF7ED",
    iconColor: "#D97706",
    borderColor: "#FED7AA",
    title: "Data Sedang Diperbarui",
    desc: "Data harga untuk komoditas ini sedang dalam proses pembaruan. Ini biasanya hanya membutuhkan beberapa detik.",
    hint: "💡 Coba lagi sebentar lagi — data akan segera tersedia.",
    hintBg: "#FFF7ED",
    hintColor: "#92400E",
  },
  network: {
    Icon: WifiOff,
    iconBg: "#FEF2F2",
    iconColor: "#DC2626",
    borderColor: "#FECACA",
    title: "Layanan Sedang Tidak Tersedia",
    desc: "Sistem prediksi harga MarketCast sedang tidak dapat diakses saat ini. Mungkin sedang dalam pemeliharaan.",
    hint: "💡 Coba muat ulang halaman atau kembali beberapa menit lagi.",
    hintBg: "#FEF2F2",
    hintColor: "#991B1B",
  },
  predict: {
    Icon: AlertTriangle,
    iconBg: "#FEF2F2",
    iconColor: "#DC2626",
    borderColor: "#FECACA",
    title: "Prediksi Belum Dapat Dihitung",
    desc: "Sistem sedang memproses data harga terbaru untuk komoditas yang Anda pilih. Mohon tunggu sebentar.",
    hint: "💡 Coba lagi dalam beberapa detik.",
    hintBg: "#FEF2F2",
    hintColor: "#991B1B",
  },
  highlights: {
    Icon: Database,
    iconBg: "#F5F3FF",
    iconColor: "#7C3AED",
    borderColor: "#DDD6FE",
    title: "Sorotan Harga Tidak Tersedia",
    desc: "Data sorotan harga hari ini sedang tidak dapat ditampilkan saat ini.",
    hint: "💡 Anda tetap dapat melihat grafik tren harga dengan memilih kategori dan komoditas di sebelah kiri.",
    hintBg: "#F5F3FF",
    hintColor: "#5B21B6",
  },
  generic: {
    Icon: AlertTriangle,
    iconBg: "#F9FAFB",
    iconColor: "#6B7280",
    borderColor: "#E5E7EB",
    title: "Terjadi Kesalahan",
    desc: "Terjadi kendala sementara. Silakan coba lagi.",
    hint: null,
    hintBg: null,
    hintColor: null,
  },
};

export default function ErrorCard({
  type = "generic",
  onRetry,
  message,
  compact = false,
}) {
  const [retrying, setRetrying] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const cfg = ERROR_CONFIG[type] || ERROR_CONFIG.generic;
  const { Icon } = cfg;

  const handleRetry = async () => {
    if (retrying) return;
    setRetrying(true);
    setRetryCount((c) => c + 1);
    try {
      await onRetry?.();
    } catch (_) {}
    setTimeout(() => setRetrying(false), 800);
  };

  return (
    <>
      <style>{`
        @keyframes mc-bounce-in {
          0%   { transform: scale(0.88); opacity: 0; }
          65%  { transform: scale(1.03); }
          100% { transform: scale(1);    opacity: 1; }
        }
        @keyframes mc-spin-btn {
          to { transform: rotate(360deg); }
        }
        @keyframes mc-shake {
          0%,100% { transform: translateX(0); }
          20%      { transform: translateX(-4px); }
          40%      { transform: translateX(4px); }
          60%      { transform: translateX(-3px); }
          80%      { transform: translateX(3px); }
        }
        .mc-error-wrap { animation: mc-bounce-in 0.4s cubic-bezier(0.34,1.56,0.64,1) forwards; }
        .mc-retry-spin { animation: mc-spin-btn 0.7s linear infinite; }
        .mc-shake      { animation: mc-shake 0.4s ease; }
        .mc-retry-btn  { transition: transform 0.15s ease, box-shadow 0.15s ease; cursor: pointer; }
        .mc-retry-btn:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(27,67,50,0.25);
        }
        .mc-retry-btn:active:not(:disabled) { transform: translateY(0); }
      `}</style>

      <div className="mc-error-wrap" style={{
        background: "var(--card-bg)",
        borderRadius: "var(--radius)",
        border: `1px solid ${cfg.borderColor}`,
        boxShadow: "var(--shadow-sm)",
        overflow: "hidden",
        padding: compact ? "20px 18px" : "32px 24px",
        textAlign: "center",
      }}>

        {/* ── Icon ── */}
        <div style={{
          width: compact ? 48 : 64,
          height: compact ? 48 : 64,
          borderRadius: "50%",
          background: cfg.iconBg,
          border: `2px solid ${cfg.borderColor}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto",
          marginBottom: compact ? 12 : 18,
        }}>
          <Icon size={compact ? 22 : 28} color={cfg.iconColor} />
        </div>

        {/* ── Title ── */}
        <div style={{
          fontSize: compact ? 14 : 16,
          fontWeight: 700,
          color: "var(--text-main)",
          marginBottom: 8,
        }}>
          {message || cfg.title}
        </div>

        {/* ── Description ── */}
        {!compact && (
          <div style={{
            fontSize: 13,
            color: "var(--text-sub)",
            lineHeight: 1.65,
            maxWidth: 340,
            margin: "0 auto",
            marginBottom: cfg.hint ? 14 : 0,
          }}>
            {cfg.desc}
          </div>
        )}

        {/* ── Hint ── */}
        {cfg.hint && !compact && (
          <div style={{
            background: cfg.hintBg,
            border: `1px solid ${cfg.borderColor}`,
            borderRadius: "var(--radius-sm)",
            padding: "10px 14px",
            fontSize: 12,
            color: cfg.hintColor,
            lineHeight: 1.5,
            maxWidth: 340,
            margin: "0 auto 20px",
            textAlign: "left",
          }}>
            {cfg.hint}
          </div>
        )}

        {/* ── Spacer kalau tidak ada hint ── */}
        {(!cfg.hint || compact) && <div style={{ marginBottom: compact ? 14 : 20 }} />}

        {/* ── Retry button ── */}
        {onRetry && (
          <button
            className={`mc-retry-btn${retryCount > 2 ? " mc-shake" : ""}`}
            onClick={handleRetry}
            disabled={retrying}
            style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              padding: compact ? "8px 20px" : "10px 28px",
              background: retrying
                ? "#94a3b8"
                : "linear-gradient(135deg, var(--primary-dark), var(--primary))",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-sm)",
              fontSize: compact ? 13 : 13.5,
              fontWeight: 700,
              boxShadow: retrying ? "none" : "0 2px 8px rgba(27,67,50,0.2)",
            }}
          >
            <RefreshCw
              size={compact ? 13 : 15}
              className={retrying ? "mc-retry-spin" : ""}
            />
            {retrying ? "Mencoba ulang..." : retryCount > 0 ? `Coba Lagi (${retryCount})` : "Coba Lagi"}
          </button>
        )}

        {/* ── Retry count warning ── */}
        {retryCount >= 3 && !retrying && (
          <div style={{
            fontSize: 11.5, color: "#DC2626",
            marginTop: 10, fontWeight: 500,
          }}>
            ⚠️ Masih gagal? Cek status backend di terminal.
          </div>
        )}
      </div>
    </>
  );
}
