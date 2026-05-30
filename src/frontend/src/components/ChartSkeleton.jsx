export default function ChartSkeleton({ komoditasNama }) {
  return (
    <>
      <style>{`
        @keyframes mc-shimmer {
          0%   { background-position: -600px 0; }
          100% { background-position:  600px 0; }
        }
        @keyframes mc-pulse-dot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.4; transform: scale(0.85); }
        }
        .mc-shimmer-el {
          background: linear-gradient(
            90deg,
            #f0fdf4 0%,
            #d1fae5 30%,
            #ecfdf5 60%,
            #f0fdf4 100%
          );
          background-size: 600px 100%;
          animation: mc-shimmer 1.6s ease-in-out infinite;
          border-radius: 6px;
        }
        .mc-pulse-dot { animation: mc-pulse-dot 1.2s ease-in-out infinite; }
      `}</style>

      <div style={{
        background: "var(--card-bg)",
        borderRadius: "var(--radius)",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-sm)",
        overflow: "hidden",
      }}>

        {/* ── Header skeleton ── */}
        <div style={{
          padding: "14px 20px",
          borderBottom: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between",
          alignItems: "center", flexWrap: "wrap", gap: 10,
        }}>
          <div>
            <div className="mc-shimmer-el" style={{ height: 14, width: 220, marginBottom: 8 }} />
            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <div className="mc-shimmer-el" style={{ width: 20, height: 3 }} />
                <div className="mc-shimmer-el" style={{ width: 50, height: 10 }} />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <div className="mc-shimmer-el" style={{ width: 20, height: 3 }} />
                <div className="mc-shimmer-el" style={{ width: 55, height: 10 }} />
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {["1 Bln","3 Bln","6 Bln","1 Thn"].map((label) => (
              <div key={label} className="mc-shimmer-el"
                style={{ height: 28, width: 52, borderRadius: 20 }} />
            ))}
          </div>
        </div>

        {/* ── Chart skeleton ── */}
        <div style={{ padding: "20px 20px 10px", position: "relative" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", height: 280 }}>

            {/* Y-axis */}
            <div style={{
              display: "flex", flexDirection: "column",
              justifyContent: "space-between",
              height: "calc(100% - 24px)", paddingTop: 4, width: 36,
            }}>
              {[1,2,3,4,5].map((i) => (
                <div key={i} className="mc-shimmer-el" style={{ height: 10, width: 32 }} />
              ))}
            </div>

            {/* Chart area */}
            <div style={{ flex: 1, position: "relative", height: "100%" }}>
              {/* Fake gridlines */}
              <svg width="100%" height="256" style={{
                position: "absolute", top: 0, left: 0, opacity: 0.4,
              }}>
                {[0,1,2,3,4].map((i) => (
                  <line key={i}
                    x1="0" y1={i * 51 + 10}
                    x2="100%" y2={i * 51 + 10}
                    stroke="#d1fae5" strokeWidth="1" strokeDasharray="4,4"
                  />
                ))}
                {/* Fake historical line */}
                <polyline
                  points="0,200 60,170 120,150 180,120 240,100 300,115 360,90 420,75 480,85"
                  fill="none" stroke="#a7f3d0" strokeWidth="2.5"
                  strokeLinejoin="round" strokeLinecap="round"
                />
                {/* Fake forecast line (dashed) */}
                <polyline
                  points="480,85 520,70 560,65 600,55"
                  fill="none" stroke="#fde68a" strokeWidth="2.5"
                  strokeDasharray="6,4"
                  strokeLinejoin="round" strokeLinecap="round"
                />
              </svg>

              {/* X-axis labels */}
              <div style={{
                position: "absolute", bottom: 0, left: 0, right: 0,
                display: "flex", justifyContent: "space-between",
              }}>
                {[1,2,3,4,5,6,7].map((i) => (
                  <div key={i} className="mc-shimmer-el" style={{ height: 10, width: 38 }} />
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── Loading indicator ── */}
        <div style={{
          padding: "12px 20px",
          borderTop: "1px solid var(--border)",
          background: "var(--primary-light)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <div className="mc-pulse-dot" style={{
            width: 9, height: 9, borderRadius: "50%",
            background: "var(--primary)", flexShrink: 0,
          }} />
          <span style={{ fontSize: 12.5, color: "var(--primary-dark)", fontWeight: 600 }}>
            Memuat data tren — {komoditasNama || "komoditas"} ...
          </span>
        </div>
      </div>
    </>
  );
}
