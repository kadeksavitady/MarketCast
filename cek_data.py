import sqlite3
import pandas as pd

# Sesuaikan dengan lokasi database kamu
db_path = "data/raw/siskaperbapo.db" 

conn = sqlite3.connect(db_path)

# 1. Cek jumlah total data yang terkumpul
total = conn.execute("SELECT COUNT(*) FROM harga_bahan_pokok").fetchone()[0]
print(f"Total data di database: {total} baris")

# 2. Lihat 5 data teratas menggunakan Pandas agar rapi seperti tabel
df = pd.read_sql_query("SELECT * FROM harga_bahan_pokok LIMIT 5", conn)
print("\n5 Data Teratas:")
print(df)

conn.close()