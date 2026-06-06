export default function StatCard({ label, value, valueColor, badge, badgeColor, accent, barColor }) {
  return (
    <div className="db-stat-card">
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
      <div style={{ position:"absolute", bottom:0, left:0, right:0, height:3,
        background:barColor, borderRadius:"0 0 18px 18px" }} />
    </div>
  );
}
