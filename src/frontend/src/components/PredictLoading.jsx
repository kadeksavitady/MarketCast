import { useEffect, useState } from "react";

const STEPS = [
  { icon: "🛒", label: "Menganalisis keranjang belanja" },
  { icon: "🧠", label: "Memuat model machine learning" },
  { icon: "📊", label: "Menghitung prediksi harga" },
  { icon: "💡", label: "Mengoptimasi rekomendasi substitusi" },
];

export default function PredictLoading() {
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(5);

  useEffect(() => {
    const stepInterval = setInterval(() => {
      setCurrentStep((prev) => (prev < STEPS.length - 1 ? prev + 1 : prev));
    }, 2800);

    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev < 88) return prev + 0.8;
        return prev;
      });
    }, 120);

    return () => {
      clearInterval(stepInterval);
      clearInterval(progressInterval);
    };
  }, []);

  return (
    <>
      <style>{`
        @keyframes mc-spin {
          to { transform: rotate(360deg); }
        }
        @keyframes mc-fadeup {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes mc-dot {
          0%, 80%, 100% { transform: scale(0.4); opacity: 0.3; }
          40%            { transform: scale(1);   opacity: 1; }
        }
        @keyframes mc-glow {
          0%, 100% { box-shadow: 0 0 0 0 rgba(27,67,50,0.25); }
          50%       { box-shadow: 0 0 0 8px rgba(27,67,50,0); }
        }
        @keyframes mc-progress-shine {
          0%   { background-position: -200% center; }
          100% { background-position: 200% center; }
        }
        .mc-spin   { animation: mc-spin 1.1s linear infinite; display: inline-block; }
        .mc-fadeup { animation: mc-fadeup 0.35s ease forwards; }
        .mc-dot-1  { animation: mc-dot 1.4s ease-in-out 0s   infinite; }
        .mc-dot-2  { animation: mc-dot 1.4s ease-in-out 0.2s infinite; }
        .mc-dot-3  { animation: mc-dot 1.4s ease-in-out 0.4s infinite; }
        .mc-glow   { animation: mc-glow 2s ease-in-out infinite; }
      `}</style>

      <div style={{
        background: "var(--card-bg)",
        borderRadius: "var(--radius)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-sm)",
        overflow: "hidden",
      }}>

        {/* ── Header ── */}
        <div style={{
          padding: "18px 20px 16px",
          borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", gap: 14,
        }}>
          <div className="mc-glow" style={{
            width: 44, height: 44, borderRadius: 12, flexShrink: 0,
            background: "linear-gradient(135deg, var(--primary-dark), var(--primary))",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span className="mc-spin" style={{ fontSize: 20 }}>⚙️</span>
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-main)", marginBottom: 3 }}>
              Menghitung Prediksi
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 5 }}>
              <span>Mohon tunggu</span>
              {[1,2,3].map(i => (
                <span key={i} className={`mc-dot-${i}`} style={{
                  width: 5, height: 5, borderRadius: "50%",
                  background: "var(--primary)", display: "inline-block",
                }} />
              ))}
            </div>
          </div>
        </div>

        {/* ── Steps ── */}
        <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
          {STEPS.map((step, i) => {
            const isDone    = i < currentStep;
            const isActive  = i === currentStep;
            const isPending = i > currentStep;

            return (
              <div key={i}
                className={isActive ? "mc-fadeup" : ""}
                style={{
                  display: "flex", alignItems: "center", gap: 12,
                  padding: "10px 14px",
                  borderRadius: "var(--radius-sm)",
                  background: isDone
                    ? "var(--primary-light)"
                    : isActive
                      ? "#f0fdf4"
                      : "var(--bg)",
                  border: `1.5px solid ${isDone ? "#a7f3d0" : isActive ? "var(--primary)" : "var(--border)"}`,
                  opacity: isPending ? 0.38 : 1,
                  transition: "all 0.3s ease",
                }}
              >
                {/* Status indicator */}
                <div style={{
                  width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: isDone
                    ? "var(--primary)"
                    : isActive
                      ? "var(--primary-dark)"
                      : "#e2e8f0",
                  transition: "background 0.3s ease",
                }}>
                  {isDone
                    ? <span style={{ color: "white", fontSize: 12, fontWeight: 700 }}>✓</span>
                    : isActive
                      ? <span className="mc-spin" style={{ fontSize: 14, color: "white", lineHeight: 1 }}>◐</span>
                      : <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>{i + 1}</span>
                  }
                </div>

                {/* Label */}
                <div style={{ flex: 1 }}>
                  <span style={{
                    fontSize: 13,
                    fontWeight: isActive ? 700 : isDone ? 600 : 400,
                    color: isDone
                      ? "var(--primary-dark)"
                      : isActive
                        ? "var(--text-main)"
                        : "var(--text-muted)",
                  }}>
                    {step.icon} {step.label}
                  </span>
                  {isActive && (
                    <div style={{ fontSize: 11, color: "var(--primary)", marginTop: 2, fontWeight: 500 }}>
                      Sedang diproses...
                    </div>
                  )}
                  {isDone && (
                    <div style={{ fontSize: 11, color: "var(--primary-dark)", marginTop: 2, opacity: 0.7 }}>
                      Selesai
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Progress bar ── */}
        <div style={{ padding: "0 18px 18px" }}>
          <div style={{
            display: "flex", justifyContent: "space-between",
            fontSize: 11, color: "var(--text-muted)", marginBottom: 6,
          }}>
            <span>Memproses data</span>
            <span style={{ fontWeight: 700, color: "var(--primary-dark)" }}>
              {Math.round(progress)}%
            </span>
          </div>
          <div style={{
            height: 7, background: "var(--border)",
            borderRadius: 20, overflow: "hidden",
          }}>
            <div style={{
              height: "100%", borderRadius: 20,
              width: `${progress}%`,
              background: "linear-gradient(90deg, var(--primary-dark) 0%, var(--primary) 50%, #4ade80 100%)",
              backgroundSize: "200% auto",
              animation: "mc-progress-shine 2s linear infinite",
              transition: "width 0.12s ease",
            }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, textAlign: "center" }}>
            Model machine learning membutuhkan beberapa saat pada percobaan pertama
          </div>
        </div>
      </div>
    </>
  );
}
