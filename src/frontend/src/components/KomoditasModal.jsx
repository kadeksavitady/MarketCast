import { X, Plus } from "lucide-react";
import { ICON_CATALOG } from "../assets/iconCatalog";
import { formatRp } from "../utils/format";

export default function KomoditasModal({
  open, onClose, selectedKat, katIconMeta,
  loadingKomoditas, komoditasList, onAdd,
}) {
  if (!open) return null;

  return (
    <div
      style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.4)", zIndex:200,
        display:"flex", alignItems:"center", justifyContent:"center",
        backdropFilter:"blur(6px)" }}
      onClick={onClose}
    >
      <div
        style={{ background:"white", borderRadius:22,
          boxShadow:"0 24px 70px rgba(0,0,0,.18)", width:440, maxHeight:"80vh",
          display:"flex", flexDirection:"column", overflow:"hidden" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal header */}
        <div style={{ padding:"20px 22px", borderBottom:"1px solid #f0fdf4",
          display:"flex", alignItems:"center", justifyContent:"space-between",
          background:"linear-gradient(135deg,#1B4332,#2d6a4f)" }}>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            {katIconMeta && (() => {
              const Icon = katIconMeta.icon;
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
          <button
            onClick={onClose}
            style={{ width:32, height:32, border:"none", background:"rgba(255,255,255,.15)",
              borderRadius:10, cursor:"pointer", display:"flex",
              alignItems:"center", justifyContent:"center",
              color:"white", transition:"background .15s" }}
            onMouseEnter={e => e.currentTarget.style.background="rgba(255,255,255,.25)"}
            onMouseLeave={e => e.currentTarget.style.background="rgba(255,255,255,.15)"}
          >
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
                <div key={item.id} className="db-item-row" onClick={() => onAdd(item)}>
                  <div>
                    <div style={{ fontSize:14, fontWeight:700, color:"#1a1a1a" }}>
                      {item.nama}
                    </div>
                    <div style={{ fontSize:12, color:"#9ca3af",
                      fontFamily:"DM Mono,monospace", marginTop:2 }}>
                      {formatRp(item.harga_ref)}/{item.satuan}
                    </div>
                  </div>
                  <button
                    style={{ background:"#1B4332", color:"white", border:"none",
                      width:32, height:32, borderRadius:10, cursor:"pointer",
                      display:"flex", alignItems:"center", justifyContent:"center",
                      boxShadow:"0 2px 8px rgba(27,67,50,.25)", transition:"all .15s" }}
                    onMouseEnter={e => e.currentTarget.style.background="#2d6a4f"}
                    onMouseLeave={e => e.currentTarget.style.background="#1B4332"}
                  >
                    <Plus size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
