export default function Toast({ msg, type }) {
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
