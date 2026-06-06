import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  TrendingUp, BarChart2, Wallet, ArrowRight,
  CheckCircle, MapPin, ShoppingBasket, Plus, Minus,
  Database, Cpu,
} from "lucide-react";

function useScrolled(threshold = 80) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);
  return scrolled;
}

function useInView(threshold = 0.12) {
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

const NAV = [
  { label: "Beranda",    id: "hero"       },
  { label: "Fitur",      id: "fitur"      },
  { label: "Cara Kerja", id: "penggunaan" },
  { label: "Tentang",    id: "tentang"    },
  { label: "FAQ",        id: "faq"        },
];

const FAQS = [
  { q: "Apa itu MarketCast?",
    a: "MarketCast adalah platform prediksi harga bahan pangan berbasis machine learning untuk masyarakat Surabaya. Membantu perencanaan belanja dengan data historis 5 tahun dan prediksi 30 hari ke depan." },
  { q: "Data harga bersumber dari mana?",
    a: "Data bersumber dari Siskaperbapo (Sistem Ketersediaan dan Perkembangan Harga Bahan Pokok) Kota Surabaya, yang mencatat pergerakan harga dari berbagai pasar tradisional secara berkala." },
  { q: "Seberapa akurat prediksi harganya?",
    a: "Model kami menggunakan XGBoost dan SARIMA dengan rata-rata MAPE di bawah 5%, artinya akurasi prediksi mencapai lebih dari 95% untuk sebagian besar komoditas." },
  { q: "Apakah MarketCast gratis?",
    a: "Ya, sepenuhnya gratis untuk seluruh masyarakat Kota Surabaya. Tidak diperlukan registrasi atau pembayaran apapun." },
  { q: "Bagaimana cara menggunakan fitur simulasi budget?",
    a: "Buka Dashboard, masukkan anggaran belanja, pilih komoditas dari 43 pilihan, lalu klik Hitung Prediksi. Sistem memberikan estimasi total belanja dan saran substitusi untuk mengoptimalkan pengeluaran." },
  { q: "Komoditas apa saja yang tersedia?",
    a: "MarketCast mencakup 43 komoditas dalam 16 kategori: beras, daging, telur, minyak goreng, sayur mayur, ikan segar, ikan asin, gula, tepung, susu, garam, cabe, bawang, mie instan, palawija, dan lainnya." },
];

export default function LandingPage() {
  const navigate = useNavigate();
  const scrolled = useScrolled();
  const [openFaq, setOpenFaq] = useState(null);

  const goTo = (id) =>
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

  const [statsRef, statsInView]     = useInView(0.3);
  const [heroRef,  heroInView]      = useInView(0.05);
  const [fiturRef, fiturInView]     = useInView(0.1);
  const [tentangRef, tentangInView] = useInView(0.1);
  const [stepRef,  stepInView]      = useInView(0.1);
  const [faqRef,   faqInView]       = useInView(0.1);
  const [ctaRef,   ctaInView]       = useInView(0.15);

  const komoditasCount        = useCounter(43,    statsInView);
  const penggunaPotensialCount = useCounter(80000, statsInView);
  const tahunDataCount         = useCounter(5,     statsInView);

  const navText = scrolled ? "#1C1917"              : "rgba(255,255,255,.9)";
  const navBg   = scrolled ? "rgba(250,250,248,.97)": "transparent";
  const navBlur = scrolled ? "blur(14px)"           : "none";
  const navShad = scrolled ? "0 1px 24px rgba(0,0,0,.08)" : "none";

  return (
    <div style={{ fontFamily:"'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif",
      color:"#1C1917", background:"#FAFAF8", overflowX:"hidden" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');
        *, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
        html { scroll-behavior:smooth; }

        .lp-btn-gold {
          display:inline-flex;align-items:center;gap:9px;padding:14px 30px;
          background:#C8A96E;color:#1C1917;border:none;border-radius:8px;
          font-family:inherit;font-size:15px;font-weight:700;cursor:pointer;
          transition:all .22s;
        }
        .lp-btn-gold:hover { background:#b8975c; transform:translateY(-2px); box-shadow:0 8px 28px rgba(200,169,110,.35); }

        .lp-btn-outline-white {
          display:inline-flex;align-items:center;gap:9px;padding:13px 28px;
          background:transparent;color:rgba(255,255,255,.9);
          border:1.5px solid rgba(255,255,255,.4);border-radius:8px;
          font-family:inherit;font-size:15px;font-weight:600;cursor:pointer;
          transition:all .22s;
        }
        .lp-btn-outline-white:hover { background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.7); }

        .lp-btn-dark {
          display:inline-flex;align-items:center;gap:9px;padding:14px 30px;
          background:#1B4332;color:white;border:none;border-radius:8px;
          font-family:inherit;font-size:15px;font-weight:700;cursor:pointer;
          transition:all .22s;
        }
        .lp-btn-dark:hover { background:#2d6a4f;transform:translateY(-2px);box-shadow:0 8px 28px rgba(27,67,50,.25); }

        .lp-btn-ghost {
          display:inline-flex;align-items:center;gap:9px;padding:13px 28px;
          background:transparent;color:#1B4332;
          border:1.5px solid #1B4332;border-radius:8px;
          font-family:inherit;font-size:15px;font-weight:600;cursor:pointer;
          transition:all .22s;
        }
        .lp-btn-ghost:hover { background:#1B4332;color:white; }

        .lp-navbtn {
          font-size:14px;font-weight:600;cursor:pointer;
          padding:5px 0;border-bottom:2px solid transparent;
          background:none;border-top:none;border-left:none;border-right:none;
          font-family:inherit;transition:all .2s,white-space:nowrap;
        }

        .lp-feature-card {
          background:white;border-radius:16px;border:1px solid #E8E0D5;
          padding:36px 30px;box-shadow:0 2px 16px rgba(0,0,0,.04);
          transition:all .28s ease;
        }
        .lp-feature-card:hover { transform:translateY(-6px);box-shadow:0 16px 48px rgba(27,67,50,.1);border-color:#c8b89a; }

        .lp-step {
          background:white;border-radius:16px;border:1px solid #E8E0D5;
          padding:32px 26px;text-align:center;transition:all .28s ease;
        }
        .lp-step:hover { transform:translateY(-5px);box-shadow:0 12px 36px rgba(0,0,0,.08); }

        .lp-faq { border:1px solid #E8E0D5;border-radius:12px;overflow:hidden;margin-bottom:10px;background:white;transition:border-color .2s,box-shadow .2s; }
        .lp-faq.open { border-color:#C8A96E;box-shadow:0 4px 20px rgba(200,169,110,.12); }
        .lp-faq-q {
          padding:20px 24px;display:flex;align-items:center;justify-content:space-between;
          cursor:pointer;font-size:15px;font-weight:600;color:#1C1917;background:white;
          gap:16px;font-family:inherit;border:none;width:100%;text-align:left;transition:background .15s;
        }
        .lp-faq.open .lp-faq-q { background:#FBF8F3; }
        .lp-faq-a { max-height:0;overflow:hidden;transition:max-height .38s ease,padding .25s;padding:0 24px;font-size:14px;color:#6B5E52;line-height:1.78; }
        .lp-faq.open .lp-faq-a { max-height:220px;padding:0 24px 20px; }

        @media(max-width:768px){
          .lp-2col { grid-template-columns:1fr!important; }
          .lp-3col { grid-template-columns:1fr!important; }
          .lp-4col { grid-template-columns:1fr 1fr!important; }
          .lp-hide-m { display:none!important; }
        }

        @keyframes lp-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.85); }
        }
        .lp-pulse-dot { animation: lp-pulse 1.4s ease-in-out infinite; }
      `}</style>

      {/* ─── NAVBAR ─── */}
      <nav style={{
        position:"fixed",top:0,left:0,right:0,zIndex:1000,height:76,
        padding:"0 3%",display:"flex",alignItems:"center",justifyContent:"space-between",
        background:navBg,backdropFilter:navBlur,boxShadow:navShad,transition:"all .35s",
      }}>
        <div style={{ display:"flex",alignItems:"center",gap:5,cursor:"pointer",flexShrink:0 }} onClick={() => goTo("hero")}>
            <img
              src={scrolled ? "/logo.svg" : "/logo-white.svg"}
              style={{ width: 80, height: 80, objectFit: "contain", transition: "opacity 0.3s ease" }}
              alt="MarketCast"
            />
          <div style={{ fontSize:25, fontWeight:900, lineHeight:1, letterSpacing:"-.3px" }}>
            {scrolled ? (
              <>
                <span style={{ color:"#1B4332", transition:"color .35s" }}>Market</span>
                <span style={{ color:"#C8A96E", transition:"color .35s" }}>Cast</span>
              </>
            ) : (
              <span style={{ color:"white", transition:"color .35s" }}>MarketCast</span>
            )}
          </div>
        </div>

        <div className="lp-hide-m" style={{ 
          display: "flex", alignItems: "center", gap: 30,
          flexGrow: 1, justifyContent: "center", padding: "0 20px" 
          }}>
          {NAV.map(n => (
            <button key={n.id} className="lp-navbtn"
              style={{ color:navText }}
              onMouseEnter={e=>{ e.currentTarget.style.color=over?"#1B4332":"white"; e.currentTarget.style.borderBottomColor=over?"#1B4332":"white"; }}
              onMouseLeave={e=>{ e.currentTarget.style.color=navText; e.currentTarget.style.borderBottomColor="transparent"; }}
              onClick={() => goTo(n.id)}>
              {n.label}
            </button>
          ))}
        </div>

        <button className="lp-btn-gold" style={{ padding:"9px 20px",fontSize:13 }} onClick={() => navigate("/app")}>
          Mulai <ArrowRight size={13} />
        </button>
      </nav>

      {/* ─── HERO ─── */}
      <section id="hero" ref={heroRef} style={{
        minHeight:"100vh",position:"relative",display:"flex",
        alignItems:"center",padding:"140px 7% 100px",overflow:"hidden",
      }}>
        <div style={{ position:"absolute",inset:0,backgroundImage:"url('/market-hero.jpg')",backgroundSize:"cover",backgroundPosition:"center 40%",zIndex:0 }} />
        <div style={{ position:"absolute",inset:0,zIndex:1,background:"linear-gradient(105deg,rgba(8,18,12,.92) 42%,rgba(8,18,12,.58) 100%)" }} />

        <div style={{
          position:"relative",zIndex:2,maxWidth:620,
          opacity:heroInView?1:0,transform:heroInView?"none":"translateY(28px)",
          transition:"all .8s cubic-bezier(.22,1,.36,1)",
        }}>
          <div style={{ display:"inline-flex",alignItems:"center",gap:8,border:"1px solid rgba(200,169,110,.45)",borderRadius:5,padding:"7px 16px",marginBottom:28,background:"rgba(200,169,110,.1)" }}>
            <MapPin size={13} color="#C8A96E" />
            <span style={{ fontSize:11.5,fontWeight:700,color:"rgba(255,255,255,.82)",letterSpacing:"1.5px",textTransform:"uppercase" }}>Platform Prediksi Harga Pangan · Surabaya</span>
          </div>

          <h1 style={{ fontSize:"clamp(36px,5vw,62px)",fontWeight:900,lineHeight:1.1,letterSpacing:"-1px",color:"white",marginBottom:20 }}>
            Rencanakan Belanja<br/>
            <span style={{ color:"#C8A96E" }}>Lebih Cerdas.</span>
          </h1>

          <p style={{ fontSize:16.5,color:"rgba(255,255,255,.68)",lineHeight:1.8,marginBottom:36,maxWidth:480 }}>
            Prediksi harga 43 komoditas bahan pangan di Surabaya berbasis machine learning. Data dari Siskaperbapo — akurat, terkini, dan gratis.
          </p>

          <div style={{ display:"flex",gap:14,flexWrap:"wrap",marginBottom:36 }}>
            <button className="lp-btn-gold" onClick={() => navigate("/app")}>Mulai Belanja <ArrowRight size={16}/></button>
            <button className="lp-btn-outline-white" onClick={() => navigate("/tren")}>Lihat Tren Harga</button>
          </div>

          <div style={{ display:"flex",gap:22,flexWrap:"wrap" }}>
            {["43 Komoditas","5 Tahun Data","Gratis"].map(t => (
              <div key={t} style={{ display:"flex",alignItems:"center",gap:6,fontSize:12.5,color:"rgba(255,255,255,.45)",fontWeight:500 }}>
                <CheckCircle size={13} color="#C8A96E" /> {t}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── STATS ─── */}
      <div ref={statsRef} style={{ background:"#1B4332",padding:"40px 6%" }}>
        <div className="lp-4col" style={{ display:"grid",gridTemplateColumns:"repeat(4,1fr)",maxWidth:1100,margin:"0 auto" }}>
          {[
            { v:komoditasCount,                             s:"",       l:"Komoditas"    },
            { v:penggunaPotensialCount.toLocaleString("id-ID"),  s:"+",      l:"Data Historis"},
            { v:tahunDataCount,                              s:" Tahun", l:"Data Tersedia"},
            { v: (
                <div style={{
                  display:"inline-flex", alignItems:"center", gap:10,
                  background:"rgba(200,169,110,.12)",
                  border:"1px solid rgba(200,169,110,.3)",
                  borderRadius:40, padding:"8px 24px",
                  fontSize:"clamp(22px,2.5vw,36px)", fontWeight:900, color:"#C8A96E",
                }}>
                  <span className="lp-pulse-dot" style={{ width:10, height:10,
                  borderRadius:"50%", background:"#22c55e",
                  display:"inline-block", flexShrink:0 }} />
                Live
                </div>
              ), s: "", l: "Otomatis Update Harian", sp: true 
            },
          ].map((s,i) => (
            <div key={i} style={{ textAlign:"center",padding:"18px 12px",borderRight:i<3?"1px solid rgba(255,255,255,.1)":"none" }}>
              <div style={{ fontSize:"clamp(26px,3vw,40px)",fontWeight:900,color:"#C8A96E",lineHeight:1.1,marginBottom:6,
                display:"flex", alignItems:"center", justifyContent:"center", gap:10 }}>
                {s.sp?s.v:`${s.v}${s.s}`}
              </div>
              <div style={{ fontSize:13,color:"rgba(255,255,255,.5)",fontWeight:500 }}>{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ─── FITUR ─── */}
      <section id="fitur" ref={fiturRef} style={{ padding:"100px 6%",background:"#FAFAF8" }}>
        <div style={{ textAlign:"center",marginBottom:60 }}>
          <div style={{ fontSize:12,fontWeight:800,color:"#C8A96E",textTransform:"uppercase",letterSpacing:"3px",marginBottom:14 }}>Fitur Unggulan</div>
          <h2 style={{ fontSize:"clamp(24px,3vw,40px)",fontWeight:900,color:"#1C1917",marginBottom:14,letterSpacing:"-.5px" }}>Teknologi yang Bekerja untuk Anda</h2>
          <p style={{ fontSize:16,color:"#6B5E52",maxWidth:500,margin:"0 auto",lineHeight:1.7 }}>Tiga fitur utama untuk membantu masyarakat Surabaya berbelanja lebih efisien</p>
        </div>

        <div className="lp-3col" style={{ display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:24,maxWidth:1100,margin:"0 auto" }}>
          {[
            { Icon:TrendingUp,iconBg:"#F0F7F4",ic:"#1B4332",title:"Prediksi Akurat",desc:"43 komoditas diprediksi menggunakan XGBoost dan SARIMA. Akurasi di atas 95% dengan data historis 5 tahun dari Siskaperbapo.",tags:["XGBoost","SARIMA","MAPE < 5%"] },
            { Icon:Wallet,iconBg:"rgba(255,255,255,.15)",ic:"white",title:"Simulasi Budget",desc:"Masukkan anggaran, pilih komoditas, dan dapatkan estimasi total belanja beserta rekomendasi substitusi untuk menghemat lebih banyak.",tags:["Smart Substitution","Budget Planning"],dark:true },
            { Icon:BarChart2,iconBg:"#F5F0E8",ic:"#9B6F2E",title:"Tren Historis",desc:"Grafik pergerakan harga 5 tahun terakhir per komoditas. Pahami pola musiman dan antisipasi kenaikan harga lebih awal.",tags:["Grafik Interaktif","Forecast 30 Hari"] },
          ].map((f,i) => (
            <div key={i} className="lp-feature-card" style={{
              ...(f.dark?{background:"linear-gradient(145deg,#1B4332,#2d6a4f)",border:"none"}:{}),
              opacity:fiturInView?1:0,transform:fiturInView?"none":"translateY(24px)",
              transition:`all .65s cubic-bezier(.22,1,.36,1) ${i*.12}s`,
              position:"relative",overflow:"hidden",
            }}>
              {f.dark && <div style={{ position:"absolute",top:-30,right:-30,width:120,height:120,borderRadius:"50%",background:"rgba(200,169,110,.08)",pointerEvents:"none" }} />}
              {f.dark && <div style={{ position:"absolute",top:20,right:20,fontSize:10.5,fontWeight:800,letterSpacing:"1.5px",color:"#C8A96E",textTransform:"uppercase",border:"1px solid rgba(200,169,110,.4)",padding:"3px 10px",borderRadius:4 }}>Populer</div>}
              <div style={{ width:56,height:56,borderRadius:14,background:f.iconBg,display:"flex",alignItems:"center",justifyContent:"center",marginBottom:22 }}>
                <f.Icon size={26} color={f.ic} />
              </div>
              <h3 style={{ fontSize:20,fontWeight:800,marginBottom:12,color:f.dark?"white":"#1C1917" }}>{f.title}</h3>
              <p style={{ fontSize:14,lineHeight:1.78,marginBottom:22,color:f.dark?"rgba(255,255,255,.72)":"#6B5E52" }}>{f.desc}</p>
              <div style={{ display:"flex",gap:8,flexWrap:"wrap" }}>
                {f.tags.map(t=>(
                  <span key={t} style={{ fontSize:11,fontWeight:700,padding:"3px 10px",borderRadius:4,background:f.dark?"rgba(255,255,255,.12)":"#F5F0E8",color:f.dark?"rgba(255,255,255,.85)":"#6B5E52",border:`1px solid ${f.dark?"rgba(255,255,255,.15)":"#E8E0D5"}` }}>{t}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ─── TENTANG ─── */}
      <section id="tentang" ref={tentangRef} style={{ padding:"100px 6%",background:"#F5F0E8" }}>
        <div className="lp-2col" style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:80,alignItems:"center",maxWidth:1100,margin:"0 auto" }}>
          <div style={{ opacity:tentangInView?1:0,transform:tentangInView?"none":"translateX(-28px)",transition:"all .75s cubic-bezier(.22,1,.36,1)" }}>
            <div style={{ fontSize:12,fontWeight:800,color:"#C8A96E",textTransform:"uppercase",letterSpacing:"3px",marginBottom:16 }}>Tentang MarketCast</div>
            <h2 style={{ fontSize:"clamp(24px,2.8vw,38px)",fontWeight:900,color:"#1C1917",marginBottom:20,lineHeight:1.25,letterSpacing:"-.4px" }}>Dibangun untuk Masyarakat Surabaya</h2>
            <p style={{ fontSize:15.5,color:"#6B5E52",lineHeight:1.82,marginBottom:20 }}>
              MarketCast dikembangkan sebagai platform analitik digital yang memanfaatkan teknologi machine learning untuk memprediksi harga 43 komoditas pangan. Kehadiran platform ini dirancang untuk membantu ibu rumah tangga, pengelola warung, hingga pedagang kecil dalam merencanakan anggaran belanja secara lebih akurat dan terukur.
            </p>
            <p style={{ fontSize:15.5,color:"#6B5E52",lineHeight:1.82,marginBottom:32 }}>
              Seluruh data harga diambil langsung dari Siskaperbapo Kota Surabaya dan diperbarui setiap hari, sehingga hasil prediksi yang disajikan selalu relevan dengan kondisi riil di pasar terkini.
            </p>
            <div style={{ display:"flex",flexDirection:"column",gap:14,marginBottom:36 }}>
              {[
                { Icon:Database,     text:"Data resmi Siskaperbapo Kota Surabaya" },
                { Icon:Cpu,          text:"Model ML: XGBoost, SARIMA & Prophet"   },
                { Icon:CheckCircle,  text:"Gratis untuk seluruh masyarakat"       },
              ].map(({ Icon, text }) => (
                <div key={text} style={{ display:"flex",alignItems:"center",gap:12 }}>
                  <div style={{ width:34,height:34,borderRadius:8,background:"#1B4332",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
                    <Icon size={15} color="#C8A96E" />
                  </div>
                  <span style={{ fontSize:14.5,color:"#1C1917",fontWeight:600 }}>{text}</span>
                </div>
              ))}
            </div>
            <div style={{ display:"flex",gap:12,flexWrap:"wrap" }}>
              <button className="lp-btn-dark" onClick={() => navigate("/app")}>Coba Dashboard <ArrowRight size={16}/></button>
              <button className="lp-btn-ghost" onClick={() => navigate("/tren")}>Lihat Tren Harga</button>
            </div>
          </div>

          <div style={{ opacity:tentangInView?1:0,transform:tentangInView?"none":"translateX(28px)",transition:"all .75s cubic-bezier(.22,1,.36,1) .15s",position:"relative" }}>
            <img src="/market-ibu.jpg" alt="Aktivitas pasar tradisional Surabaya"
              style={{ width:"100%",height:520,objectFit:"cover",borderRadius:20,display:"block",boxShadow:"0 24px 70px rgba(0,0,0,.18)" }} />
            <div style={{ position:"absolute",bottom:24,left:-28,background:"white",borderRadius:14,padding:"16px 20px",boxShadow:"0 12px 40px rgba(0,0,0,.15)",minWidth:200 }}>
              <div style={{ fontSize:11,color:"#9ca3af",fontWeight:600,textTransform:"uppercase",letterSpacing:"1px",marginBottom:6 }}>Harga Hari Ini</div>
              <div style={{ fontSize:18,fontWeight:900,color:"#1B4332",marginBottom:4 }}>Rp 15.583</div>
              <div style={{ fontSize:12,color:"#6B5E52" }}>Beras Premium / kg</div>
              <div style={{ display:"flex",alignItems:"center",gap:4,marginTop:8,fontSize:11.5,color:"#1B4332",fontWeight:700 }}>
                <TrendingUp size={12} /> +1.2% dari kemarin
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CARA KERJA ─── */}
      <section id="penggunaan" ref={stepRef} style={{ padding:"100px 6%",background:"#FAFAF8" }}>
        <div style={{ textAlign:"center",marginBottom:60 }}>
          <div style={{ fontSize:12,fontWeight:800,color:"#C8A96E",textTransform:"uppercase",letterSpacing:"3px",marginBottom:14 }}>Cara Kerja</div>
          <h2 style={{ fontSize:"clamp(24px,3vw,40px)",fontWeight:900,color:"#1C1917",marginBottom:14,letterSpacing:"-.5px" }}>Tiga Langkah Mudah</h2>
          <p style={{ fontSize:16,color:"#6B5E52",maxWidth:400,margin:"0 auto" }}>Dari memilih komoditas hingga mendapat prediksi harga dalam hitungan detik</p>
        </div>

        <div className="lp-3col" style={{ display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:28,maxWidth:960,margin:"0 auto",position:"relative" }}>
          <div className="lp-hide-m" style={{ position:"absolute",top:52,left:"20%",right:"20%",height:1,zIndex:0,background:"linear-gradient(90deg,#E8E0D5,#C8A96E 50%,#E8E0D5)" }} />
          {[
            { n:"01",Icon:ShoppingBasket,title:"Pilih Komoditas",desc:"Pilih dari 43 komoditas dalam 16 kategori yang tersedia" },
            { n:"02",Icon:Wallet,        title:"Masukkan Budget", desc:"Tentukan anggaran dan jumlah komoditas yang ingin dibeli" },
            { n:"03",Icon:TrendingUp,    title:"Dapatkan Prediksi",desc:"Terima estimasi harga akurat dan rekomendasi belanja optimal" },
          ].map((s,i) => (
            <div key={i} className="lp-step" style={{ zIndex:1,opacity:stepInView?1:0,transform:stepInView?"none":"translateY(24px)",transition:`all .65s cubic-bezier(.22,1,.36,1) ${i*.15}s` }}>
              <div style={{ width:56,height:56,borderRadius:"50%",margin:"0 auto 18px",background:"#1B4332",display:"flex",alignItems:"center",justifyContent:"center",boxShadow:"0 6px 20px rgba(27,67,50,.22)",position:"relative",zIndex:1 }}>
                <s.Icon size={22} color="#C8A96E" />
              </div>
              <div style={{ fontSize:11,color:"#C8A96E",fontWeight:800,letterSpacing:"2px",textTransform:"uppercase",marginBottom:12 }}>{s.n}</div>
              <h3 style={{ fontSize:18,fontWeight:800,color:"#1C1917",marginBottom:10 }}>{s.title}</h3>
              <p style={{ fontSize:13.5,color:"#6B5E52",lineHeight:1.7 }}>{s.desc}</p>
            </div>
          ))}
        </div>

        <div style={{ textAlign:"center",marginTop:48 }}>
          <button className="lp-btn-gold" onClick={() => navigate("/app")}>Coba Sekarang — Gratis <ArrowRight size={16}/></button>
        </div>
      </section>

      {/* ─── FAQ ─── */}
      <section id="faq" ref={faqRef} style={{ padding:"100px 6%",background:"#F5F0E8" }}>
        <div style={{ maxWidth:740,margin:"0 auto" }}>
          <div style={{ textAlign:"center",marginBottom:52 }}>
            <div style={{ fontSize:12,fontWeight:800,color:"#C8A96E",textTransform:"uppercase",letterSpacing:"3px",marginBottom:14 }}>FAQ</div>
            <h2 style={{ fontSize:"clamp(24px,3vw,38px)",fontWeight:900,color:"#1C1917",marginBottom:12,letterSpacing:"-.5px" }}>Pertanyaan yang Sering Diajukan</h2>
          </div>
          <div style={{ opacity:faqInView?1:0,transform:faqInView?"none":"translateY(18px)",transition:"all .65s ease" }}>
            {FAQS.map((item,i) => (
              <div key={i} className={`lp-faq${openFaq===i?" open":""}`}>
                <button className="lp-faq-q" onClick={() => setOpenFaq(openFaq===i?null:i)}>
                  <span>{item.q}</span>
                  <span style={{ width:30,height:30,borderRadius:6,flexShrink:0,background:openFaq===i?"#1B4332":"#F5F0E8",display:"flex",alignItems:"center",justifyContent:"center",color:openFaq===i?"white":"#6B5E52",transition:"all .2s" }}>
                    {openFaq===i ? <Minus size={14}/> : <Plus size={14}/>}
                  </span>
                </button>
                <div className="lp-faq-a">{item.a}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section ref={ctaRef} style={{ padding:0 }}>
        <div style={{
          position:"relative",overflow:"hidden",minHeight:420,
          display:"flex",alignItems:"center",justifyContent:"center",padding:"80px 6%",
          opacity:ctaInView?1:0,transition:"opacity .7s ease",
        }}>
          <div style={{ position:"absolute",inset:0,backgroundImage:"url('/market-uang.jpg')",backgroundSize:"cover",backgroundPosition:"center",zIndex:0 }} />
          <div style={{ position:"absolute",inset:0,zIndex:1,background:"linear-gradient(135deg,rgba(8,18,12,.94),rgba(27,67,50,.9))" }} />
          <div style={{ position:"relative",zIndex:2,textAlign:"center",maxWidth:640 }}>
            <div style={{ fontSize:12,fontWeight:800,color:"#C8A96E",textTransform:"uppercase",letterSpacing:"3px",marginBottom:18 }}>Mulai Sekarang</div>
            <h2 style={{ fontSize:"clamp(24px,3.5vw,42px)",fontWeight:900,color:"white",marginBottom:16,letterSpacing:"-.5px",lineHeight:1.2 }}>
              Belanja Lebih Terencana,<br/>Hidup Lebih Hemat
            </h2>
            <p style={{ fontSize:15.5,color:"rgba(255,255,255,.68)",lineHeight:1.75,maxWidth:480,margin:"0 auto 36px" }}>
              Bergabunglah dengan masyarakat Surabaya yang sudah memanfaatkan teknologi prediksi harga untuk belanja lebih cerdas setiap harinya.
            </p>
            <div style={{ display:"flex",gap:14,justifyContent:"center",flexWrap:"wrap" }}>
              <button className="lp-btn-gold" onClick={() => navigate("/app")}>Mulai Belanja <ArrowRight size={16}/></button>
              <button className="lp-btn-outline-white" onClick={() => navigate("/tren")}>Lihat Tren Harga</button>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FOOTER ─── */}
      <footer style={{ background:"#0F1A14",color:"rgba(255,255,255,.55)",padding:"52px 6% 28px" }}>
        <div className="lp-3col" style={{ display:"grid",gridTemplateColumns:"2fr 1fr 1fr",gap:52,maxWidth:1100,margin:"0 auto 40px" }}>
          <div>
            <div style={{ display:"flex",alignItems:"center",gap:5,marginBottom:9 }}>
              <img
                src="/logo-white.svg"
                style={{ width: 80, height: 80, objectFit: "contain", transition: "opacity 0.3s ease" }}
                alt="MarketCast"
              />
              <div>
                <div style={{ fontSize:17,fontWeight:900,color:"white" }}>MarketCast</div>
                <div style={{ fontSize:10,color:"rgba(255,255,255,.25)" }}>Platform Prediksi Harga Pangan</div>
              </div>
            </div>
            <p style={{ fontSize:13.5,lineHeight:1.8,maxWidth:300 }}>Platform prediksi harga bahan pangan berbasis machine learning untuk masyarakat Kota Surabaya.</p>
          </div>
          <div>
            <div style={{ fontSize:12,fontWeight:700,color:"rgba(255,255,255,.3)",textTransform:"uppercase",letterSpacing:"1.5px",marginBottom:18 }}>Navigasi</div>
            {NAV.map(n => (
              <div key={n.id} style={{ marginBottom:10 }}>
                <span style={{ fontSize:13.5,cursor:"pointer",color:"rgba(255,255,255,.5)",transition:"color .15s" }}
                  onMouseEnter={e=>e.target.style.color="#C8A96E"}
                  onMouseLeave={e=>e.target.style.color="rgba(255,255,255,.5)"}
                  onClick={() => goTo(n.id)}>{n.label}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize:12,fontWeight:700,color:"rgba(255,255,255,.3)",textTransform:"uppercase",letterSpacing:"1.5px",marginBottom:18 }}>Akses Cepat</div>
            {[{label:"Dashboard Belanja",path:"/app"},{label:"Market Trends",path:"/tren"}].map(l=>(
              <div key={l.label} style={{ marginBottom:10 }}>
                <span style={{ fontSize:13.5,cursor:"pointer",color:"rgba(255,255,255,.5)",transition:"color .15s" }}
                  onMouseEnter={e=>e.target.style.color="#C8A96E"}
                  onMouseLeave={e=>e.target.style.color="rgba(255,255,255,.5)"}
                  onClick={() => navigate(l.path)}>{l.label}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ borderTop:"1px solid rgba(255,255,255,.06)",paddingTop:22,textAlign:"center",fontSize:12.5,color:"rgba(255,255,255,.22)" }}>
          © 2026 MarketCast · Platform Prediksi Harga Pangan Berbasis Machine Learning · Kota Surabaya
        </div>
      </footer>
    </div>
  );
}
