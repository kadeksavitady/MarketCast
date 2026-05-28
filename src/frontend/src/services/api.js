const BASE_URL = "http://localhost:8000";

export const getKategori = async () => {
  const res = await fetch(`${BASE_URL}/katalog/categories`);
  return res.json();
};

export const getKomoditas = async (kategori = null) => {
  const url = kategori
    ? `${BASE_URL}/katalog/commodities?kategori=${encodeURIComponent(kategori)}`
    : `${BASE_URL}/katalog/commodities`;
  const res = await fetch(url);
  return res.json();
};

export const predictBelanja = async (budget, keranjang) => {
  const res = await fetch(`${BASE_URL}/belanja/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ budget, keranjang }),
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
};

export const getTren = async (komoditas_id, hari = 90) => {
  const res = await fetch(
    `${BASE_URL}/tren/${komoditas_id}?hari=${hari}`
  );
  return res.json();
};

export const getHealth = async () => {
  const res = await fetch(`${BASE_URL}/health`);
  return res.json();
};