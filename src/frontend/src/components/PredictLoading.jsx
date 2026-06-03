import { useEffect, useState } from "react";
import { ShoppingBasket, BrainCircuit, BarChart2, Lightbulb, Check } from "lucide-react";

const STEPS = [
  { Icon: ShoppingBasket, label: "Menganalisis keranjang belanja"   },
  { Icon: BrainCircuit,   label: "Memuat model machine learning"    },
  { Icon: BarChart2,      label: "Menghitung prediksi harga"        },
  { Icon: Lightbulb,      label: "Mengoptimasi rekomendasi substitusi" },
];

export default function PredictLoading() {
  const [currentStep, setCurrentStep] = useState(0);
  const [progress,    setProgress]    = useState(4);

  useEffect(() => {
    const stepT = setInterval(() => {
      setCurrentStep((p) => (p < STEPS.length - 1 ? p + 1 : p));
    }, 2800);

    const progT = setInterval(() => {
      setProgress((p) => (p < 88 ? p + 0.7 : p));
    }, 110);

    return () => { clearInterval(stepT); clearInterval(progT); };
  }, []);

  return (
    <>
      <style>{`
        @keyframes pl-fadeup { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
        @keyframes pl-dot    {
          0%,80%,100% { transform:scale(.4); opacity:.3; }
          40%         { transform:scale(1);  opacity:1;  }
        }
        @keyframes pl-shine  {
          0%   { background-position:-300px 0; }
          100% { background-position: 300px 0; }
        }
        @keyframes pl-pulse-icon {
          0%,100% { transform: scale(1);    opacity: 1;  }
          50%     { transform: scale(1.25); opacity: .7; }
        }
        .pl-pulse-icon { animation: pl-pulse-icon 1.2s ease-in-out infinite; }
        .pl-fadeup     { animation: pl-fadeup .35s ease forwards; }
        .pl-dot-1      { animation: pl-dot 1.4s ease-in-out 0s   infinite; }
        .pl-dot-2      { animation: pl-dot 1.4s ease-in-out .2s  infinite; }
        .pl-dot-3      { animation: pl-dot 1.4s ease-in-out .4s  infinite; }
        .pl-shine      {
          background: linear-gradient(90deg,
            #1B4332 0%, #2d6a4f 30%, #4ade80 50%, #2d6a4f 70%, #1B4332 100%);
          background-size: 300px 100%;
          animation: pl-shine 1.8s linear infinite;
        }
      `}</style>

      <div style={{
        background: "white", borderRadius: 18,
        border: "1.5px solid #e8f5e9",
        boxShadow: "0 2px 12px rgba(27,67,50,.06)",
        overflow: "hidden",
        fontFamily: "'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif",
      }}>

        {/* ── Header ── */}
        <div style={{
          padding: "18px 20px 16px",
          borderBottom: "1px solid #f0fdf4",
          display: "flex", alignItems: "center", gap: 14,
          background: "linear-gradient(135deg,#1B4332,#2d6a4f)",
        }}>
          {/* Spinning ring */}
          <div style={{ position: "relative", flexShrink: 0 }}>
            <div style={{
                width:42, height:42, borderRadius:"50%",
                background:"rgba(255,255,255,.12)",
                display:"flex", alignItems:"center", justifyContent:"center",
              }}>
                <BarChart2 size={20} color="#F9A825" className="pl-pulse-icon" />
              </div>
          </div>

          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 800, color: "white", marginBottom: 4 }}>
              Menghitung Prediksi
            </div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,.6)",
              display: "flex", alignItems: "center", gap: 5 }}>
              <span>Mohon tunggu</span>
              {[1,2,3].map(i => (
                <span key={i} className={`pl-dot-${i}`} style={{
                  width: 4, height: 4, borderRadius: "50%",
                  background: "#F9A825", display: "inline-block",
                }} />
              ))}
            </div>
          </div>

          <div style={{ fontSize: 13, fontWeight: 800, color: "#F9A825" }}>
            {Math.round(progress)}%
          </div>
        </div>

        {/* ── Steps ── */}
        <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
          {STEPS.map(({ Icon, label }, i) => {
            const isDone   = i < currentStep;
            const isActive = i === currentStep;
            const isPend   = i > currentStep;

            return (
              <div key={i}
                className={isActive ? "pl-fadeup" : ""}
                style={{
                  display: "flex", alignItems: "center", gap: 12,
                  padding: "10px 14px", borderRadius: 12,
                  background: isDone ? "#f0fdf4" : isActive ? "#f8fdf9" : "#fafafa",
                  border: `1.5px solid ${isDone ? "#a7f3d0" : isActive ? "#1B4332" : "#f0f0f0"}`,
                  opacity: isPend ? .35 : 1,
                  transition: "all .3s ease",
                }}>

                {/* Icon circle */}
                <div style={{
                  width: 34, height: 34, borderRadius: 10, flexShrink: 0,
                  background: isDone ? "#1B4332" : isActive ? "#1B4332" : "#e5e7eb",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "background .3s",
                  position: "relative",
                }}>
                  {isDone ? (
                    <Check size={15} color="white" strokeWidth={3} />
                  ) : isActive ? (
                    <Icon size={15} color="white" className="pl-pulse-icon" />
                  ) : (
                    <Icon size={15} color="#9ca3af" />
                  )}
                </div>

                {/* Label */}
                <div style={{ flex: 1 }}>
                  <div style={{
                    fontSize: 13, fontWeight: isActive ? 700 : isDone ? 600 : 400,
                    color: isDone ? "#1B4332" : isActive ? "#1a1a1a" : "#9ca3af",
                  }}>
                    {label}
                  </div>
                  {isDone && (
                    <div style={{ fontSize: 11, color: "#1B4332", opacity: .7, marginTop: 1 }}>
                      Selesai
                    </div>
                  )}
                  {isActive && (
                    <div style={{ fontSize: 11, color: "#1B4332", marginTop: 1, fontWeight: 600 }}>
                      Sedang diproses...
                    </div>
                  )}
                </div>

                {/* Step number */}
                {isPend && (
                  <span style={{ fontSize: 11, color: "#9ca3af", fontWeight: 600 }}>
                    {i + 1}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Progress bar ── */}
        <div style={{ padding: "0 18px 18px" }}>
          <div style={{ height: 6, background: "#f0fdf4", borderRadius: 20, overflow: "hidden",
            border: "1px solid #e8f5e9" }}>
            <div className="pl-shine" style={{
              height: "100%", borderRadius: 20,
              width: `${progress}%`,
              transition: "width .11s ease",
            }} />
          </div>
          <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 8, textAlign: "center" }}>
            Model machine learning membutuhkan beberapa saat pada percobaan pertama
          </div>
        </div>
      </div>
    </>
  );
}
