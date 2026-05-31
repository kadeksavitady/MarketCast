import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  TrendingUp, ShoppingCart, BarChart2,
  ArrowRight, ChevronDown, CheckCircle,
} from "lucide-react";

// ── Hooks ──────────────────────────────────────────────────────────

function useScrolled(threshold = 60) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > threshold);
    window.addEventListener("scroll", fn, { passive: true });
    return () => window.removeEventListener("scroll", fn);
  }, [threshold]);
  return scrolled;
}

function useInView(threshold = 0.14) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) setInView(true); },
      { threshold }
    );
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [threshold]);
  return [ref, inView];
}

function useCounter(target, active, duration = 1800) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!active) return;
    let cur = 0;
    const step = target / (duration / 14);
    const t = setInterval(() => {
      cur += step;
      if (cur >= target) { setVal(target); clearInterval(t); }
      else setVal(Math.floor(cur));
    }, 14);
    return () => clearInterval(t);
  }, [active, target, duration]);
  return val;
}

// ── Data ──────────────────────────────────────────────────────────

const NAV = [
  { label: "Beranda",   id: "hero" },
  { label: "Fitur",     id: "fitur" },
  { label: "Cara Kerja",id: "penggunaan" },
  { label: "Tentang",   id: "tentang" },
  { label: "FAQ",       id: "faq" },
];

const FAQS = [
  {
    q: "Apa itu MarketCast?",
    a: "MarketCast adalah platform prediksi harga bahan pangan berbasis machine learning yang dirancang khusus untuk masyarakat Surabaya. Platform ini membantu Anda merencanakan belanja lebih cerdas dengan data harga historis 5 tahun dan prediksi 30 hari ke depan.",
  },
  {
    q: "Data harga bersumber dari mana?",
    a: "Data harga bersumber dari Siskaperbapo (Sistem Ketersediaan dan Perkembangan Harga Bahan Pokok) Kota Surabaya, yang mencatat pergerakan harga dari berbagai pasar tradisional di Surabaya secara berkala.",
  },
  {
    q: "Seberapa akurat prediksi harganya?",
    a: "Model prediksi kami menggunakan algoritma XGBoost dan SARIMA dengan rata-rata tingkat kesalahan (MAPE) di bawah 5%, artinya akurasi prediksi mencapai lebih dari 95% untuk sebagian besar komoditas.",
  },
  {
    q: "Apakah MarketCast gratis digunakan?",
    a: "Ya, MarketCast sepenuhnya gratis untuk seluruh masyarakat Kota Surabaya. Tidak diperlukan registrasi atau pembayaran apapun.",
  },
  {
    q: "Bagaimana cara menggunakan fitur simulasi budget?",
    a: "Buka halaman Dashboard, masukkan anggaran belanja Anda, pilih komoditas dari 43 pilihan yang tersedia, lalu klik 'Hitung Prediksi'. Sistem akan memberikan estimasi total belanja beserta saran substitusi untuk mengoptimalkan pengeluaran.",
  },
  {
    q: "Komoditas apa saja yang tersedia?",
    a: "MarketCast mencakup 43 komoditas dalam 16 kategori: beras, daging, telur, minyak goreng, sayur mayur, ikan segar, ikan asin, gula, tepung, susu, garam, cabe, bawang, mie instan, palawija, dan barang penting lainnya.",
  },
];

const MOCK_PRICES = [
  { nama: "Beras Premium",       harga: "Rp 15.583", satuan: "kg",  delta: "+1.2%", up: true  },
  { nama: "Cabe Merah Keriting",  harga: "Rp 49.166", satuan: "kg",  delta: "+1.7%", up: true  },
  { nama: "Telur Ayam Ras",       harga: "Rp 27.083", satuan: "kg",  delta: "−0.3%", up: false },
  { nama: "Minyak Goreng Curah",  harga: "Rp 20.833", satuan: "kg",  delta: "+0.5%", up: true  },
];

// ── Component ─────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate   = useNavigate();
  const scrolled   = useScrolled();
  const [openFaq, setOpenFaq] = useState(null);

  const goTo = (id) =>
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

  const [statsRef, statsInView]       = useInView(0.3);
  const [heroRef,  heroInView]        = useInView(0.05);
  const [fiturRef, fiturInView]       = useInView(0.1);
  const [tentangRef, tentangInView]   = useInView(0.1);
  const [stepRef, stepInView]         = useInView(0.1);
  const [faqRef,  faqInView]          = useInView(0.1);
  const [ctaRef,  ctaInView]          = useInView(0.15);

  const c43    = useCounter(43,    statsInView);
  const c56100 = useCounter(56100, statsInView);
  const c5     = useCounter(5,     statsInView);

  return (
    <div style={{ fontFamily: "'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif",
      color: "#1a1a1a", overflowX: "hidden", background: "#fff" }}>

      {/* ─── Google Font ─── */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html { scroll-behavior: smooth; }

        @keyframes lp-up    { from{opacity:0;transform:translateY(36px)} to{opacity:1;transform:none} }
        @keyframes lp-left  { from{opacity:0;transform:translateX(-36px)} to{opacity:1;transform:none} }
        @keyframes lp-right { from{opacity:0;transform:translateX(36px)} to{opacity:1;transform:none} }
        @keyframes lp-float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-14px)} }
        @keyframes lp-pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.85)} }
        @keyframes lp-shine {
          0%   { background-position:-400px 0 }
          100% { background-position: 400px 0 }
        }
        @keyframes lp-spin  { to{transform:rotate(360deg)} }
        @keyframes lp-badge { from{opacity:0;transform:scale(.8)} to{opacity:1;transform:scale(1)} }

        .lp-up      { animation: lp-up   .7s cubic-bezier(.22,1,.36,1) both }
        .lp-left    { animation: lp-left .7s cubic-bezier(.22,1,.36,1) both }
        .lp-right   { animation: lp-right .7s cubic-bezier(.22,1,.36,1) both }
        .lp-float   { animation: lp-float 4.5s ease-in-out infinite }
        .lp-pulse-dot{ animation: lp-pulse 1.4s ease-in-out infinite }

        .lp-btn-gold {
          display:inline-flex;align-items:center;gap:8px;
          padding:14px 28px;
          background:linear-gradient(135deg,#F9A825,#f59f00);
          color:#1B4332;border:none;border-radius:14px;
          font-family:inherit;font-size:15px;font-weight:800;cursor:pointer;
          box-shadow:0 4px 20px rgba(249,168,37,.35);
          transition:all .22s ease;
        }
        .lp-btn-gold:hover{transform:translateY(-3px);box-shadow:0 10px 30px rgba(249,168,37,.45)}

        .lp-btn-dark {
          display:inline-flex;align-items:center;gap:8px;
          padding:14px 28px;
          background:linear-gradient(135deg,#1B4332,#2d6a4f);
          color:white;border:none;border-radius:14px;
          font-family:inherit;font-size:15px;font-weight:700;cursor:pointer;
          box-shadow:0 4px 20px rgba(27,67,50,.25);
          transition:all .22s ease;
        }
        .lp-btn-dark:hover{transform:translateY(-3px);box-shadow:0 10px 30px rgba(27,67,50,.35)}

        .lp-btn-ghost {
          display:inline-flex;align-items:center;gap:8px;
          padding:13px 26px;
          background:transparent;
          color:#1B4332;border:2px solid #1B4332;border-radius:14px;
          font-family:inherit;font-size:15px;font-weight:600;cursor:pointer;
          transition:all .22s ease;
        }
        .lp-btn-ghost:hover{background:#1B4332;color:white;transform:translateY(-3px)}

        .lp-nav-link {
          font-size:14px;font-weight:600;color:#4a5568;cursor:pointer;
          padding:5px 0;border-bottom:2px solid transparent;
          transition:all .18s;background:none;border-top:none;
          border-left:none;border-right:none;font-family:inherit;
        }
        .lp-nav-link:hover{color:#1B4332;border-bottom-color:#1B4332}

        .lp-feature-card {
          background:white;border-radius:22px;
          border:1.5px solid #e8f5e9;
          padding:34px 28px;
          box-shadow:0 2px 20px rgba(27,67,50,.05);
          transition:all .3s ease;
        }
        .lp-feature-card:hover{
          transform:translateY(-8px);
          box-shadow:0 20px 50px rgba(27,67,50,.12);
          border-color:#a7f3d0;
        }

        .lp-step {
          background:white;border-radius:22px;
          border:1.5px solid #f0f0f0;
          padding:32px 24px;text-align:center;
          transition:all .28s ease;
          position:relative;overflow:hidden;
        }
        .lp-step::before {
          content:'';position:absolute;inset:0;
          background:linear-gradient(135deg,rgba(27,67,50,.03),rgba(249,168,37,.03));
          opacity:0;transition:opacity .28s;
        }
        .lp-step:hover{transform:translateY(-6px);box-shadow:0 14px 40px rgba(27,67,50,.1)}
        .lp-step:hover::before{opacity:1}

        .lp-faq {
          border:1.5px solid #e8f5e9;border-radius:16px;
          overflow:hidden;margin-bottom:12px;
          transition:border-color .2s,box-shadow .2s;
        }
        .lp-faq.open{border-color:#a7f3d0;box-shadow:0 4px 20px rgba(27,67,50,.08)}

        .lp-faq-q {
          padding:20px 24px;display:flex;align-items:center;
          justify-content:space-between;cursor:pointer;
          font-size:15px;font-weight:600;color:#1a1a1a;
          background:white;gap:16px;transition:background .15s;
          font-family:inherit;border:none;width:100%;text-align:left;
        }
        .lp-faq.open .lp-faq-q{background:#f0fdf4;color:#1B4332}

        .lp-faq-a {
          max-height:0;overflow:hidden;
          transition:max-height .38s ease,padding .25s;
          padding:0 24px;font-size:14px;color:#555;line-height:1.75;
        }
        .lp-faq.open .lp-faq-a{max-height:220px;padding:0 24px 20px}

        .lp-price-row{
          display:flex;justify-content:space-between;align-items:center;
          padding:10px 14px;border-radius:12px;margin-bottom:8px;
          transition:background .15s;
        }
        .lp-price-row:hover{background:#f8fdf9}

        .lp-tag {
          font-size:11px;font-weight:700;padding:3px 10px;
          border-radius:20px;background:#f0fdf4;
          color:#1B4332;border:1px solid #a7f3d0;
        }

        @media(max-width:768px){
          .lp-2col{grid-template-columns:1fr!important}
          .lp-3col{grid-template-columns:1fr!important}
          .lp-4col{grid-template-columns:1fr 1fr!important}
          .lp-hide-mobile{display:none!important}
        }
      `}</style>

      {/* ════════════════ NAVBAR ════════════════ */}
      <nav style={{
        position:"fixed",top:0,left:0,right:0,zIndex:1000,
        height:68,padding:"0 6%",
        display:"flex",alignItems:"center",justifyContent:"space-between",
        background: scrolled ? "rgba(255,255,255,.94)" : "transparent",
        backdropFilter: scrolled ? "blur(14px)" : "none",
        boxShadow: scrolled ? "0 2px 24px rgba(0,0,0,.07)" : "none",
        transition:"all .3s ease",
      }}>
        {/* Logo */}
        <div style={{display:"flex",alignItems:"center",gap:10,cursor:"pointer"}}
          onClick={() => goTo("hero")}>
          <div style={{
            width:38,height:38,borderRadius:11,flexShrink:0,
            background:"linear-gradient(135deg,#1B4332,#2d6a4f)",
            display:"flex",alignItems:"center",justifyContent:"center",
            boxShadow:"0 4px 12px rgba(27,67,50,.25)",
          }}>
            <span style={{fontSize:20}}>🛒</span>
          </div>
          <div>
            <div style={{fontSize:17,fontWeight:900,color:"#1B4332",lineHeight:1.1}}>MarketCast</div>
            <div style={{fontSize:10,color:"#9ca3af",fontWeight:500,lineHeight:1}}>Kota Surabaya</div>
          </div>
        </div>

        {/* Links */}
        <div className="lp-hide-mobile"
          style={{display:"flex",alignItems:"center",gap:30}}>
          {NAV.map(n => (
            <button key={n.id} className="lp-nav-link" onClick={() => goTo(n.id)}>
              {n.label}
            </button>
          ))}
        </div>

        {/* CTA */}
        <button className="lp-btn-dark"
          style={{padding:"9px 20px",fontSize:13}}
          onClick={() => navigate("/app")}>
          Mulai <ArrowRight size={13} />
        </button>
      </nav>

      {/* ════════════════ HERO ════════════════ */}
      <section id="hero" ref={heroRef} style={{
        minHeight:"100vh",
        background:"linear-gradient(150deg,#f8fdf9 0%,#ffffff 55%,#fffdf0 100%)",
        display:"flex",alignItems:"center",
        padding:"100px 6% 70px",
        position:"relative",overflow:"hidden",
      }}>
        {/* Blobs */}
        {[
          {top:"8%",right:"4%",size:480,color:"rgba(27,67,50,.055)"},
          {bottom:"8%",left:"1%",size:320,color:"rgba(249,168,37,.06)"},
          {top:"50%",right:"25%",size:200,color:"rgba(27,67,50,.03)"},
        ].map((b,i) => (
          <div key={i} style={{
            position:"absolute",borderRadius:"50%",pointerEvents:"none",
            width:b.size,height:b.size,
            background:`radial-gradient(circle,${b.color} 0%,transparent 70%)`,
            top:b.top,bottom:b.bottom,left:b.left,right:b.right,
          }}/>
        ))}

        <div className="lp-2col" style={{
          display:"grid",gridTemplateColumns:"1fr 1fr",
          gap:64,alignItems:"center",maxWidth:1200,margin:"0 auto",width:"100%",
        }}>
          {/* Left */}
          <div style={{
            opacity:heroInView?1:0,
            transform:heroInView?"none":"translateY(36px)",
            transition:"all .75s cubic-bezier(.22,1,.36,1)",
          }}>
            {/* Badge */}
            <div style={{
              display:"inline-flex",alignItems:"center",gap:9,
              background:"#f0fdf4",border:"1.5px solid #a7f3d0",
              borderRadius:24,padding:"7px 16px",marginBottom:26,
              animation:"lp-badge .6s .1s both",
            }}>
              <span className="lp-pulse-dot" style={{
                width:8,height:8,borderRadius:"50%",
                background:"#22c55e",flexShrink:0,display:"inline-block",
              }}/>
              <span style={{fontSize:12.5,fontWeight:700,color:"#1B4332"}}>
                Platform Prediksi Harga Pangan Surabaya
              </span>
            </div>

            <h1 style={{
              fontSize:"clamp(30px,4vw,56px)",fontWeight:900,
              lineHeight:1.12,letterSpacing:"-.8px",
              color:"#1B4332",marginBottom:20,
            }}>
              Belanja Cerdas,<br/>
              <span style={{
                background:"linear-gradient(120deg,#F9A825 20%,#f59f00 80%)",
                WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",
              }}>Hemat Lebih Banyak</span>
            </h1>

            <p style={{
              fontSize:16,color:"#6b7280",lineHeight:1.78,
              marginBottom:36,maxWidth:480,
            }}>
              Prediksi harga <strong style={{color:"#1B4332"}}>43 komoditas pangan</strong> di Surabaya
              menggunakan machine learning. Rencanakan belanja bulanan dengan lebih akurat,
              efisien, dan hemat.
            </p>

            <div style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:36}}>
              <button className="lp-btn-gold" onClick={() => navigate("/app")}>
                🛒 Mulai Belanja Sekarang
              </button>
              <button className="lp-btn-ghost" onClick={() => navigate("/tren")}>
                📈 Lihat Tren Harga
              </button>
            </div>

            {/* Trust row */}
            <div style={{display:"flex",gap:22,flexWrap:"wrap"}}>
              {[
                {icon:"✅",txt:"43 Komoditas"},
                {icon:"📅",txt:"5 Tahun Data"},
                {icon:"🆓",txt:"Gratis"},
                {icon:"📡",txt:"Data Siskaperbapo"},
              ].map(b => (
                <div key={b.txt} style={{
                  display:"flex",alignItems:"center",gap:6,
                  fontSize:12.5,color:"#9ca3af",fontWeight:500,
                }}>
                  <span style={{fontSize:14}}>{b.icon}</span>{b.txt}
                </div>
              ))}
            </div>
          </div>

          {/* Right — floating card */}
          <div className="lp-float lp-hide-mobile" style={{
            opacity:heroInView?1:0,
            transform:heroInView?"translateY(0)":"translateY(20px) translateX(24px)",
            transition:"opacity .75s ease .2s",
          }}>
            <div style={{
              background:"white",borderRadius:26,
              boxShadow:"0 24px 70px rgba(27,67,50,.13),0 4px 16px rgba(0,0,0,.04)",
              padding:28,border:"1.5px solid #e8f5e9",
            }}>
              {/* Header */}
              <div style={{
                display:"flex",justifyContent:"space-between",alignItems:"center",
                marginBottom:18,
              }}>
                <div style={{fontSize:13.5,fontWeight:800,color:"#1B4332"}}>
                  📋 Prediksi Harga Hari Ini
                </div>
                <div style={{
                  fontSize:11,background:"#f0fdf4",color:"#1B4332",
                  fontWeight:700,padding:"3px 10px",borderRadius:20,
                  border:"1px solid #a7f3d0",
                }}>Live · Surabaya</div>
              </div>

              {/* Price rows */}
              {MOCK_PRICES.map((p,i) => (
                <div key={i} className="lp-price-row"
                  style={{background: i%2===0?"#f8fdf9":"white",border:"1px solid #f0f9f4"}}>
                  <div>
                    <div style={{fontSize:13,fontWeight:600,marginBottom:2}}>{p.nama}</div>
                    <div style={{fontSize:11.5,color:"#9ca3af",fontFamily:"monospace"}}>
                      {p.harga}/{p.satuan}
                    </div>
                  </div>
                  <span style={{
                    fontSize:12,fontWeight:800,padding:"4px 10px",borderRadius:20,
                    background:p.up?"#fef2f2":"#f0fdf4",
                    color:p.up?"#dc2626":"#1B4332",
                  }}>{p.delta}</span>
                </div>
              ))}

              {/* Budget bar preview */}
              <div style={{
                marginTop:16,padding:"12px 16px",borderRadius:14,
                background:"linear-gradient(135deg,#1B4332,#2d6a4f)",
                color:"white",
              }}>
                <div style={{
                  display:"flex",justifyContent:"space-between",
                  fontSize:11.5,marginBottom:8,opacity:.8,
                }}>
                  <span>Penggunaan Budget</span><span>76%</span>
                </div>
                <div style={{height:6,background:"rgba(255,255,255,.2)",borderRadius:10,overflow:"hidden"}}>
                  <div style={{
                    height:"100%",width:"76%",borderRadius:10,
                    background:"linear-gradient(90deg,#F9A825,#f59f00)",
                  }}/>
                </div>
                <div style={{
                  marginTop:10,fontSize:12,fontWeight:700,
                  display:"flex",alignItems:"center",gap:6,
                }}>
                  <span style={{fontSize:14}}>💡</span>
                  Ada 2 alternatif lebih hemat tersedia
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ════════════════ STATS BAR ════════════════ */}
      <div ref={statsRef} style={{
        background:"linear-gradient(135deg,#1B4332 0%,#2d6a4f 100%)",
        padding:"42px 6%",
      }}>
        <div className="lp-4col" style={{
          display:"grid",gridTemplateColumns:"repeat(4,1fr)",
          maxWidth:1100,margin:"0 auto",
        }}>
          {[
            {val:c43,         suf:"",       lbl:"Komoditas"},
            {val:c56100.toLocaleString("id-ID"), suf:"+", lbl:"Data Historis"},
            {val:c5,          suf:" Tahun", lbl:"Data Tersedia"},
            {val:null,        suf:"",       lbl:"Real-time Update",special:true},
          ].map((s,i) => (
            <div key={i} style={{
              textAlign:"center",padding:"20px 12px",
              borderRight:i<3?"1px solid rgba(255,255,255,.12)":"none",
            }}>
              <div style={{
                fontSize:s.special?22:"clamp(26px,3vw,42px)",
                fontWeight:900,color:"#F9A825",lineHeight:1.1,marginBottom:6,
              }}>
                {s.special ? "⚡ Live" : `${s.val}${s.suf}`}
              </div>
              <div style={{fontSize:13,color:"rgba(255,255,255,.65)",fontWeight:500}}>
                {s.lbl}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ════════════════ FITUR UNGGULAN ════════════════ */}
      <section id="fitur" ref={fiturRef} style={{
        padding:"100px 6%",background:"#fff",
      }}>
        <div style={{textAlign:"center",marginBottom:64}}>
          <div style={{
            fontSize:12,fontWeight:800,color:"#F9A825",
            textTransform:"uppercase",letterSpacing:"3px",marginBottom:14,
          }}>Fitur Unggulan</div>
          <h2 style={{
            fontSize:"clamp(24px,3vw,42px)",fontWeight:900,
            color:"#1B4332",marginBottom:16,letterSpacing:"-.5px",
          }}>
            Teknologi Terdepan untuk<br/>Belanja yang Lebih Cerdas
          </h2>
          <p style={{fontSize:16,color:"#6b7280",maxWidth:520,margin:"0 auto",lineHeight:1.7}}>
            Tiga fitur utama yang dirancang untuk membantu masyarakat Surabaya
            merencanakan anggaran belanja dengan lebih efisien
          </p>
        </div>

        <div className="lp-3col" style={{
          display:"grid",gridTemplateColumns:"repeat(3,1fr)",
          gap:24,maxWidth:1100,margin:"0 auto",
        }}>
          {[
            {
              emoji:"📊",bg:"#f0fdf4",ec:"#1B4332",
              title:"Prediksi Akurat",
              desc:"43 komoditas diprediksi menggunakan model XGBoost dan SARIMA dengan akurasi lebih dari 95%. Didukung data historis 5 tahun dari Siskaperbapo Surabaya.",
              tags:["XGBoost","SARIMA","95%+ Akurasi"],
            },
            {
              emoji:"🛒",bg:"#fffbeb",ec:"#b45309",
              title:"Simulasi Budget",
              desc:"Masukkan anggaran belanja, pilih komoditas, dan dapatkan estimasi total beserta rekomendasi substitusi cerdas untuk menghemat lebih banyak.",
              tags:["Smart Substitution","Budget Planning"],
              highlight: true,
            },
            {
              emoji:"📈",bg:"#eff6ff",ec:"#1d4ed8",
              title:"Tren Historis",
              desc:"Lihat grafik pergerakan harga 5 tahun terakhir per komoditas. Pahami pola musiman dan antisipasi kenaikan harga lebih awal.",
              tags:["Grafik Interaktif","Forecast 30 Hari"],
            },
          ].map((f,i) => (
            <div key={i} className="lp-feature-card" style={{
              position:"relative",overflow:"hidden",
              opacity:fiturInView?1:0,
              transform:fiturInView?"none":"translateY(28px)",
              transition:`all .65s cubic-bezier(.22,1,.36,1) ${i*.12}s`,
              ...(f.highlight ? {
                background:"linear-gradient(145deg,#1B4332,#2d6a4f)",
                borderColor:"transparent",
              } : {}),
            }}>
              {f.highlight && (
                <div style={{
                  position:"absolute",top:20,right:20,
                  background:"#F9A825",color:"#1B4332",
                  fontSize:10,fontWeight:800,padding:"3px 10px",
                  borderRadius:20,letterSpacing:"1px",
                }}>POPULER</div>
              )}
              <div style={{
                width:62,height:62,borderRadius:18,
                background:f.highlight?"rgba(255,255,255,.12)":f.bg,
                display:"flex",alignItems:"center",justifyContent:"center",
                fontSize:30,marginBottom:22,
              }}>{f.emoji}</div>
              <h3 style={{
                fontSize:20,fontWeight:800,marginBottom:12,
                color:f.highlight?"white":"#1a1a1a",
              }}>{f.title}</h3>
              <p style={{
                fontSize:14,lineHeight:1.75,marginBottom:20,
                color:f.highlight?"rgba(255,255,255,.78)":"#6b7280",
              }}>{f.desc}</p>
              <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
                {f.tags.map(t => (
                  <span key={t} style={{
                    fontSize:11,fontWeight:700,padding:"3px 10px",borderRadius:20,
                    background:f.highlight?"rgba(255,255,255,.15)":"#f0fdf4",
                    color:f.highlight?"white":"#1B4332",
                    border:`1px solid ${f.highlight?"rgba(255,255,255,.2)":"#a7f3d0"}`,
                  }}>{t}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ════════════════ TENTANG ════════════════ */}
      <section id="tentang" ref={tentangRef} style={{
        padding:"100px 6%",
        background:"linear-gradient(180deg,#f8fdf9,#fff)",
      }}>
        <div className="lp-2col" style={{
          display:"grid",gridTemplateColumns:"1fr 1fr",
          gap:72,alignItems:"center",maxWidth:1100,margin:"0 auto",
        }}>
          {/* Visual */}
          <div style={{
            opacity:tentangInView?1:0,
            transform:tentangInView?"none":"translateX(-32px)",
            transition:"all .75s cubic-bezier(.22,1,.36,1)",
          }}>
            <div style={{
              background:"linear-gradient(145deg,#1B4332 0%,#2d6a4f 100%)",
              borderRadius:28,padding:40,
              boxShadow:"0 24px 70px rgba(27,67,50,.2)",
              position:"relative",overflow:"hidden",
            }}>
              <div style={{
                position:"absolute",top:-40,right:-40,width:180,height:180,
                borderRadius:"50%",background:"rgba(249,168,37,.12)",
              }}/>
              <div style={{fontSize:12,color:"rgba(255,255,255,.5)",
                fontWeight:600,letterSpacing:"2px",marginBottom:10,
                textTransform:"uppercase"}}>Tentang Platform</div>
              <div style={{
                fontSize:26,fontWeight:900,color:"white",
                marginBottom:28,lineHeight:1.3,
              }}>
                Dibangun untuk<br/>Masyarakat Surabaya
              </div>
              {[
                {icon:"🎓",txt:"Proyek Berbasis Pembelajaran — EEPIS Surabaya"},
                {icon:"📡",txt:"Data resmi dari Siskaperbapo Kota Surabaya"},
                {icon:"🤖",txt:"Model ML: XGBoost, SARIMA & Prophet"},
                {icon:"🔒",txt:"Data diperbarui setiap hari secara otomatis"},
                {icon:"🆓",txt:"Gratis untuk seluruh masyarakat Surabaya"},
              ].map((r,i) => (
                <div key={i} style={{
                  display:"flex",gap:14,alignItems:"flex-start",marginBottom:14,
                }}>
                  <span style={{fontSize:20,flexShrink:0,marginTop:1}}>{r.icon}</span>
                  <span style={{fontSize:14,color:"rgba(255,255,255,.82)",lineHeight:1.6}}>
                    {r.txt}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Text */}
          <div style={{
            opacity:tentangInView?1:0,
            transform:tentangInView?"none":"translateX(32px)",
            transition:"all .75s cubic-bezier(.22,1,.36,1) .15s",
          }}>
            <div style={{
              fontSize:12,fontWeight:800,color:"#F9A825",
              textTransform:"uppercase",letterSpacing:"3px",marginBottom:16,
            }}>Tentang MarketCast</div>
            <h2 style={{
              fontSize:"clamp(22px,2.8vw,38px)",fontWeight:900,
              color:"#1B4332",marginBottom:20,lineHeight:1.25,letterSpacing:"-.4px",
            }}>
              Solusi Cerdas untuk Perencanaan Belanja Pangan
            </h2>
            <p style={{fontSize:15,color:"#6b7280",lineHeight:1.82,marginBottom:18}}>
              MarketCast adalah platform inovatif yang menggunakan teknologi{" "}
              <em style={{color:"#1B4332",fontStyle:"normal",fontWeight:700}}>machine learning</em>{" "}
              untuk memprediksi harga 43 komoditas bahan pangan di Kota Surabaya.
              Platform ini dikembangkan untuk membantu masyarakat — dari ibu rumah tangga
              hingga pengelola warung — merencanakan anggaran belanja dengan lebih akurat.
            </p>
            <p style={{fontSize:15,color:"#6b7280",lineHeight:1.82,marginBottom:32}}>
              Dengan data historis 5 tahun dari Siskaperbapo dan model prediksi berteknologi
              tinggi, MarketCast memberikan gambaran harga 30 hari ke depan serta rekomendasi
              substitusi komoditas yang lebih terjangkau tanpa mengorbankan kebutuhan gizi.
            </p>
            <div style={{display:"flex",gap:12,flexWrap:"wrap"}}>
              <button className="lp-btn-dark" onClick={() => navigate("/app")}>
                Coba Dashboard <ArrowRight size={16}/>
              </button>
              <button className="lp-btn-ghost" onClick={() => navigate("/tren")}>
                Lihat Tren Harga
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ════════════════ CARA KERJA ════════════════ */}
      <section id="penggunaan" ref={stepRef} style={{
        padding:"100px 6%",background:"#fff",
      }}>
        <div style={{textAlign:"center",marginBottom:64}}>
          <div style={{
            fontSize:12,fontWeight:800,color:"#F9A825",
            textTransform:"uppercase",letterSpacing:"3px",marginBottom:14,
          }}>Cara Kerja</div>
          <h2 style={{
            fontSize:"clamp(24px,3vw,42px)",fontWeight:900,
            color:"#1B4332",marginBottom:14,letterSpacing:"-.5px",
          }}>Tiga Langkah Mudah</h2>
          <p style={{fontSize:16,color:"#6b7280",maxWidth:420,margin:"0 auto"}}>
            Dari memilih komoditas hingga mendapat prediksi harga — semuanya dalam hitungan detik
          </p>
        </div>

        <div className="lp-3col" style={{
          display:"grid",gridTemplateColumns:"repeat(3,1fr)",
          gap:28,maxWidth:960,margin:"0 auto",position:"relative",
        }}>
          {/* Connector */}
          <div className="lp-hide-mobile" style={{
            position:"absolute",top:52,left:"20%",right:"20%",
            height:2,zIndex:0,
            background:"linear-gradient(90deg,#a7f3d0 0%,#F9A825 50%,#a7f3d0 100%)",
          }}/>

          {[
            {n:"1",emoji:"🥦",title:"Pilih Komoditas",
              desc:"Pilih dari 43 komoditas pangan dalam 16 kategori yang telah tersedia"},
            {n:"2",emoji:"💰",title:"Masukkan Budget",
              desc:"Tentukan anggaran belanja dan jumlah komoditas yang ingin dibeli"},
            {n:"3",emoji:"✨",title:"Dapatkan Prediksi",
              desc:"Terima prediksi harga akurat dan rekomendasi belanja paling optimal"},
          ].map((s,i) => (
            <div key={i} className="lp-step" style={{
              zIndex:1,
              opacity:stepInView?1:0,
              transform:stepInView?"none":"translateY(28px)",
              transition:`all .65s cubic-bezier(.22,1,.36,1) ${i*.14}s`,
            }}>
              <div style={{
                width:58,height:58,borderRadius:"50%",margin:"0 auto 18px",
                background:"linear-gradient(135deg,#1B4332,#2d6a4f)",
                display:"flex",alignItems:"center",justifyContent:"center",
                fontSize:20,fontWeight:900,color:"#F9A825",
                boxShadow:"0 8px 24px rgba(27,67,50,.28)",
                position:"relative",zIndex:1,
              }}>{s.n}</div>
              <div style={{fontSize:32,marginBottom:14}}>{s.emoji}</div>
              <h3 style={{fontSize:18,fontWeight:800,color:"#1a1a1a",marginBottom:10}}>
                {s.title}
              </h3>
              <p style={{fontSize:13.5,color:"#6b7280",lineHeight:1.7}}>{s.desc}</p>
            </div>
          ))}
        </div>

        <div style={{textAlign:"center",marginTop:48}}>
          <button className="lp-btn-gold" onClick={() => navigate("/app")}>
            Coba Sekarang — Gratis! <ArrowRight size={16}/>
          </button>
        </div>
      </section>

      {/* ════════════════ FAQ ════════════════ */}
      <section id="faq" ref={faqRef} style={{
        padding:"100px 6%",
        background:"linear-gradient(180deg,#f8fdf9,#fff)",
      }}>
        <div style={{maxWidth:760,margin:"0 auto"}}>
          <div style={{textAlign:"center",marginBottom:56}}>
            <div style={{
              fontSize:12,fontWeight:800,color:"#F9A825",
              textTransform:"uppercase",letterSpacing:"3px",marginBottom:14,
            }}>FAQ</div>
            <h2 style={{
              fontSize:"clamp(24px,3vw,40px)",fontWeight:900,
              color:"#1B4332",marginBottom:12,letterSpacing:"-.5px",
            }}>Pertanyaan yang Sering Diajukan</h2>
            <p style={{fontSize:15,color:"#6b7280"}}>
              Temukan jawaban atas pertanyaan umum seputar MarketCast
            </p>
          </div>

          <div style={{
            opacity:faqInView?1:0,
            transform:faqInView?"none":"translateY(20px)",
            transition:"all .65s ease",
          }}>
            {FAQS.map((item,i) => (
              <div key={i} className={`lp-faq${openFaq===i?" open":""}`}>
                <button className="lp-faq-q" onClick={() => setOpenFaq(openFaq===i?null:i)}>
                  <span>{item.q}</span>
                  <span style={{
                    width:30,height:30,borderRadius:"50%",flexShrink:0,
                    background:openFaq===i?"#1B4332":"#f0f4f0",
                    display:"flex",alignItems:"center",justifyContent:"center",
                    color:openFaq===i?"white":"#555",
                    fontSize:18,fontWeight:700,
                    transition:"all .2s",
                  }}>
                    {openFaq===i ? "−" : "+"}
                  </span>
                </button>
                <div className="lp-faq-a">{item.a}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════ CTA BANNER ════════════════ */}
      <section style={{padding:"80px 6%"}} ref={ctaRef}>
        <div style={{
          maxWidth:900,margin:"0 auto",
          background:"linear-gradient(135deg,#1B4332 0%,#2d6a4f 55%,#1a5c3f 100%)",
          borderRadius:32,padding:"64px 52px",
          textAlign:"center",position:"relative",overflow:"hidden",
          opacity:ctaInView?1:0,
          transform:ctaInView?"none":"translateY(24px)",
          transition:"all .7s ease",
          boxShadow:"0 32px 80px rgba(27,67,50,.24)",
        }}>
          {/* Decorative circles */}
          {[
            {top:-50,right:-50,s:220,c:"rgba(249,168,37,.12)"},
            {bottom:-40,left:-40,s:180,c:"rgba(255,255,255,.06)"},
            {top:"40%",right:"10%",s:120,c:"rgba(249,168,37,.07)"},
          ].map((d,i) => (
            <div key={i} style={{
              position:"absolute",borderRadius:"50%",pointerEvents:"none",
              width:d.s,height:d.s,background:d.c,
              top:d.top,bottom:d.bottom,left:d.left,right:d.right,
            }}/>
          ))}

          <div style={{fontSize:44,marginBottom:18,position:"relative"}}>🚀</div>
          <h2 style={{
            fontSize:"clamp(22px,3vw,40px)",fontWeight:900,
            color:"white",marginBottom:16,letterSpacing:"-.5px",
            position:"relative",
          }}>
            Mulai Belanja Lebih Cerdas Hari Ini
          </h2>
          <p style={{
            fontSize:16,color:"rgba(255,255,255,.78)",lineHeight:1.75,
            maxWidth:500,margin:"0 auto 38px",position:"relative",
          }}>
            Bergabunglah dengan masyarakat Surabaya yang sudah memanfaatkan
            teknologi prediksi harga untuk belanja lebih hemat dan terencana.
          </p>
          <div style={{
            display:"flex",gap:14,justifyContent:"center",
            flexWrap:"wrap",position:"relative",
          }}>
            <button className="lp-btn-gold" onClick={() => navigate("/app")}>
              🛒 Mulai Belanja Sekarang
            </button>
            <button className="lp-btn-ghost"
              style={{borderColor:"rgba(255,255,255,.45)",color:"white"}}
              onClick={() => navigate("/tren")}>
              📈 Lihat Tren Harga
            </button>
          </div>
        </div>
      </section>

      {/* ════════════════ FOOTER ════════════════ */}
      <footer style={{
        background:"#0f172a",color:"rgba(255,255,255,.6)",
        padding:"52px 6% 28px",
      }}>
        <div className="lp-3col" style={{
          display:"grid",gridTemplateColumns:"2fr 1fr 1fr",
          gap:52,maxWidth:1100,margin:"0 auto 40px",
        }}>
          <div>
            <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:18}}>
              <div style={{
                width:40,height:40,borderRadius:12,flexShrink:0,
                background:"linear-gradient(135deg,#1B4332,#2d6a4f)",
                display:"flex",alignItems:"center",justifyContent:"center",
                boxShadow:"0 4px 12px rgba(27,67,50,.3)",
              }}>
                <span style={{fontSize:20}}>🛒</span>
              </div>
              <div>
                <div style={{fontSize:18,fontWeight:900,color:"white"}}>MarketCast</div>
                <div style={{fontSize:10,color:"rgba(255,255,255,.35)"}}>Kota Surabaya</div>
              </div>
            </div>
            <p style={{fontSize:13.5,lineHeight:1.8,maxWidth:310}}>
              Platform prediksi harga bahan pangan berbasis machine learning
              untuk masyarakat Kota Surabaya.
            </p>
          </div>

          <div>
            <div style={{fontSize:13,fontWeight:700,color:"white",marginBottom:18}}>
              Navigasi
            </div>
            {NAV.map(n => (
              <div key={n.id} style={{marginBottom:11}}>
                <span style={{
                  fontSize:13.5,cursor:"pointer",
                  color:"rgba(255,255,255,.55)",transition:"color .15s",
                }}
                onMouseEnter={e=>e.target.style.color="#F9A825"}
                onMouseLeave={e=>e.target.style.color="rgba(255,255,255,.55)"}
                onClick={() => goTo(n.id)}>
                  {n.label}
                </span>
              </div>
            ))}
          </div>

          <div>
            <div style={{fontSize:13,fontWeight:700,color:"white",marginBottom:18}}>
              Akses Cepat
            </div>
            {[
              {label:"Dashboard Belanja",path:"/app"},
              {label:"Market Trends",path:"/tren"},
            ].map(l => (
              <div key={l.label} style={{marginBottom:11}}>
                <span style={{
                  fontSize:13.5,cursor:"pointer",
                  color:"rgba(255,255,255,.55)",transition:"color .15s",
                }}
                onMouseEnter={e=>e.target.style.color="#F9A825"}
                onMouseLeave={e=>e.target.style.color="rgba(255,255,255,.55)"}
                onClick={() => navigate(l.path)}>
                  {l.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div style={{
          borderTop:"1px solid rgba(255,255,255,.07)",
          paddingTop:22,textAlign:"center",fontSize:12.5,
          color:"rgba(255,255,255,.3)",
        }}>
          © 2026 MarketCast · Platform Prediksi Harga Pangan Berbasis Machine Learning · Kota Surabaya
        </div>
      </footer>
    </div>
  );
}
