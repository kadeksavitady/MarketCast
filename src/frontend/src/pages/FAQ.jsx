import { useState } from "react";
import { ChevronDown, ChevronUp, HelpCircle, Info } from "lucide-react";

const FAQ_DATA = [
  {
    kategori: "Tentang MarketCast",
    items: [
      {
        q: "Apa itu MarketCast?",
        a: "MarketCast adalah sistem prediksi harga bahan pokok berbasis machine learning yang dirancang khusus untuk Kota Surabaya. Aplikasi ini membantu masyarakat memperkirakan harga komoditas pangan dan merencanakan belanja dengan lebih efisien.",
      },
      {
        q: "Siapa yang bisa menggunakan MarketCast?",
        a: "MarketCast dapat digunakan oleh siapa saja — mulai dari ibu rumah tangga yang ingin merencanakan belanja bulanan, pedagang pasar yang ingin memantau tren harga, hingga instansi pemerintah yang membutuhkan data pangan.",
      },
      {
        q: "Apakah MarketCast gratis?",
        a: "Ya, MarketCast sepenuhnya gratis dan tidak memerlukan akun atau registrasi. Cukup buka aplikasi dan langsung gunakan.",
      },
    ],
  },
  {
    kategori: "Data & Akurasi",
    items: [
      {
        q: "Data harga dari mana?",
        a: "Data harga bersumber dari SISKAPERBAPO (Sistem Informasi Ketersediaan dan Perkembangan Harga Bahan Pokok) Jawa Timur — platform resmi milik Pemerintah Provinsi Jawa Timur. Data historis mencakup lebih dari 56.000 catatan harga sejak Mei 2021.",
      },
      {
        q: "Seberapa sering data diperbarui?",
        a: "Data harga diperbarui setiap hari secara otomatis melalui sistem scraping terjadwal. Harga yang ditampilkan mencerminkan kondisi pasar Kota Surabaya pada hari tersebut.",
      },
      {
        q: "Seberapa akurat prediksi harganya?",
        a: "Prediksi harga menggunakan model machine learning (Prophet dan SARIMA) yang dilatih dengan data historis 5 tahun. Akurasi bervariasi per komoditas — komoditas dengan pola musiman yang jelas seperti cabai dan bawang cenderung lebih akurat diprediksi. Prediksi bersifat estimasi dan tidak menjamin harga aktual di pasar.",
      },
      {
        q: "Komoditas apa saja yang tersedia?",
        a: "MarketCast mencakup 43 komoditas bahan pokok yang dibagi dalam 14 kategori: Beras, Gula, Minyak Goreng, Daging, Telur, Susu, Palawija, Garam, Tepung, Mie Instan, Cabe, Bawang, Ikan Segar, Ikan Asin, Sayur Mayur, dan Barang Penting Lainnya.",
      },
    ],
  },
  {
    kategori: "Cara Penggunaan",
    items: [
      {
        q: "Bagaimana cara menggunakan Simulasi Keranjang?",
        a: "Di halaman Dashboard, masukkan budget belanja Anda, lalu pilih kategori dan tambahkan komoditas ke keranjang. Sistem akan otomatis menghitung total estimasi harga dan sisa budget. Klik 'Hitung Prediksi' untuk mendapatkan rekomendasi substitusi komoditas yang lebih hemat.",
      },
      {
        q: "Apa itu Smart Substitution?",
        a: "Smart Substitution adalah fitur yang merekomendasikan alternatif komoditas yang lebih terjangkau dengan nilai gizi serupa. Misalnya, jika Anda memilih Daging Sapi yang harganya tinggi, sistem akan menyarankan Daging Ayam sebagai alternatif dengan estimasi penghematan yang ditampilkan.",
      },
      {
        q: "Bagaimana cara membaca grafik di Market Trends?",
        a: "Grafik menampilkan dua garis: garis hijau adalah data harga historis (data nyata dari pasar), sedangkan garis oranye putus-putus adalah prediksi harga 30 hari ke depan. Anda bisa mengubah rentang waktu historis dengan tombol 1 Bln, 3 Bln, 6 Bln, atau 1 Thn di pojok kanan atas grafik.",
      },
    ],
  },
];

function FAQItem({ q, a }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        overflow: "hidden",
        marginBottom: 8,
      }}
    >
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 18px",
          cursor: "pointer",
          background: open ? "var(--primary-light)" : "var(--card-bg)",
          transition: "background 0.18s",
          gap: 12,
        }}
      >
        <span
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: open ? "var(--primary-dark)" : "var(--text-main)",
            flex: 1,
          }}
        >
          {q}
        </span>
        {open ? (
          <ChevronUp size={16} color="var(--primary-dark)" />
        ) : (
          <ChevronDown size={16} color="var(--text-muted)" />
        )}
      </div>
      {open && (
        <div
          style={{
            padding: "14px 18px",
            fontSize: 13.5,
            color: "var(--text-sub)",
            lineHeight: 1.7,
            borderTop: "1px solid var(--border)",
            background: "var(--card-bg)",
          }}
        >
          {a}
        </div>
      )}
    </div>
  );
}

export default function FAQ() {
  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ marginBottom: 8 }}>FAQ & Tentang</h1>
        <p style={{ color: "var(--text-sub)", fontSize: 14, lineHeight: 1.6 }}>
          Pertanyaan yang sering ditanyakan seputar MarketCast — sistem prediksi harga bahan pokok Kota Surabaya.
        </p>
      </div>

      {/* About card */}
      <div
        style={{
          background: "#1B4332",
          borderRadius: "var(--radius)",
          padding: "24px 28px",
          marginBottom: 32,
          display: "flex",
          gap: 20,
          alignItems: "flex-start",
        }}
      >
        <div
          style={{
            width: 44,
            height: 44,
            background: "rgba(255,255,255,0.12)",
            borderRadius: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Info size={22} color="white" />
        </div>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "white", marginBottom: 8 }}>
            Tentang MarketCast
          </div>
          <p style={{ fontSize: 13.5, color: "rgba(255,255,255,0.75)", lineHeight: 1.7, margin: 0 }}>
            MarketCast dikembangkan sebagai proyek PBL (Project Based Learning) lintas mata kuliah
            Data Mining, Machine Learning, dan Teknologi Web Service — Program Studi D4 Sains Data
            Terapan, Politeknik Elektronika Negeri Surabaya (PENS). Data bersumber dari SISKAPERBAPO
            Jawa Timur dan diproses menggunakan model prediksi time series untuk membantu masyarakat
            merencanakan kebutuhan pangan dengan lebih bijak.
          </p>
          <div
            style={{
              display: "flex",
              gap: 8,
              marginTop: 14,
              flexWrap: "wrap",
            }}
          >
            {["43 Komoditas", "56.100+ Data", "5 Tahun Historis", "Update Harian"].map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "3px 10px",
                  borderRadius: 20,
                  background: "rgba(255,255,255,0.12)",
                  color: "rgba(255,255,255,0.85)",
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* FAQ sections */}
      {FAQ_DATA.map((section) => (
        <div key={section.kategori} style={{ marginBottom: 28 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 12,
              paddingBottom: 10,
              borderBottom: "1px solid var(--border)",
            }}
          >
            <HelpCircle size={15} color="var(--primary-dark)" />
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--primary-dark)" }}>
              {section.kategori}
            </span>
          </div>
          {section.items.map((item) => (
            <FAQItem key={item.q} q={item.q} a={item.a} />
          ))}
        </div>
      ))}
    </div>
  );
}