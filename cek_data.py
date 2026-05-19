# import sqlite3
# import pandas as pd

# # Sesuaikan dengan lokasi database kamu
# db_path = "data/raw/siskaperbapo.db" 

# conn = sqlite3.connect(db_path)

# # 1. Cek jumlah total data yang terkumpul
# total = conn.execute("SELECT COUNT(*) FROM harga_bahan_pokok").fetchone()[0]
# print(f"Total data di database: {total} baris")

# # 2. Lihat 5 data teratas menggunakan Pandas agar rapi seperti tabel
# df = pd.read_sql_query("SELECT * FROM harga_bahan_pokok LIMIT 5 ", conn)
# print("\n5 Data Teratas:")
# print(df)

# conn.close()



# import sqlite3
# import pandas as pd

# # 1. Buka database mentah
# conn = sqlite3.connect("data/raw/siskaperbapo.db")
# df_mentah = pd.read_sql("SELECT * FROM harga_bahan_pokok", conn)
# conn.close()

# # 2. Cek Total Komoditas Asli dari Siskaperbapo
# komoditas_unik = df_mentah['komoditas'].unique()
# print(f"📊 1. Total Komoditas di Database Mentah: {len(komoditas_unik)}")

# # 3. Cek Berapa Komoditas yang Selamat dari Filter "Harga > 0"
# df_harga_positif = df_mentah[df_mentah['harga_rp'] > 0]
# komoditas_positif = df_harga_positif['komoditas'].unique()
# print(f"📈 2. Total Komoditas yang punya harga > 0: {len(komoditas_positif)}")

# print("\n🔍 DAFTAR KOMODITAS MENTAH YANG TERSEDIA:")
# for k in sorted(list(komoditas_unik)):
#     print(f" - {k}")



import sqlite3
import pandas as pd

conn = sqlite3.connect("data/raw/siskaperbapo.db")

# 1. Cek Total Baris (Apakah datanya jutaan atau cuma ratusan?)
total_baris = pd.read_sql("SELECT COUNT(*) as jumlah FROM harga_bahan_pokok", conn).iloc[0,0]
print(f"Total baris di database: {total_baris}")

# 2. Cek Rentang Tanggal (Apakah data 5 tahunnya masih ada?)
tanggal = pd.read_sql("SELECT MIN(tanggal_data) as awal, MAX(tanggal_data) as akhir FROM harga_bahan_pokok", conn)
print(f"Rentang tanggal data: {tanggal.iloc[0]['awal']} sampai {tanggal.iloc[0]['akhir']}")

conn.close()