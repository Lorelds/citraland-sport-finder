# Catatan: Penjelasan File Citraland Sport Finder

| File | Tugas | Kapan jalan |
|---|---|---|
| `config.py` | Menyimpan pengaturan | Saat di-import file lain |
| `data_fetch.py` | Mengambil data dari Google/OSM | Saat dijalankan manual, dan saat geocoding alamat |
| `gis.py` | Mengolah data peta dan menghitung rute | Saat dipanggil `app.py` |
| `app.py` | Menerima request dan menampilkan halaman | Selama server hidup |

Catatan: form dikirim lewat URL dengan GET (`app.py:116-118` membaca `request.args`). Server tidak mengingat rute antar-request.

## `config.py`: pengaturan

Isinya API key, CRS, lokasi file, titik awal cadangan, dan daftar olahraga.

| Yang mau diubah | Baris | Catatan |
|---|---|---|
| Warna marker | `SPORTS`, baris 52-60 | Langsung berlaku setelah restart |
| Warna garis rute | `ACCENT_COLOR`, baris 62 | Langsung berlaku setelah restart |
| Jumlah kandidat rute | `ROUTE_CANDIDATES`, baris 41 | Lebih besar berarti lebih teliti, tapi lebih lambat |
| Titik awal cadangan | `FALLBACK_ORIGIN`, baris 45 | Dipakai kalau alamat kosong atau geocoding gagal |
| Luas jaringan jalan | `GRAPH_BUFFER_M`, baris 39 | Hapus dulu `data/graph.graphml` kalau sudah ada, karena file itu yang dibaca |

## `data_fetch.py`: ambil data

- `search_places`: mencari tempat per olahraga lewat Google Places.
- `names_other_sport`: membuang hasil yang salah kategori, misalnya lapangan tenis yang muncul di pencarian futsal.
- `fetch_all_venues`: menjalankan pencarian untuk semua olahraga dan membuang duplikat.
- `geocode`: mengubah alamat menjadi lat/lon.
- `build_area`: menyusun polygon batas CitraLand.

Perintah: `python data_fetch.py --refresh` untuk data tempat, `--boundary` untuk batas area.

Contoh mengubah: untuk memperluas kata kunci pencarian tenis, ubah `query` di `config.py`, lalu jalankan `--refresh`. Perintah ini butuh API key.

## `gis.py`: inti GIS

- `load_boundary`, `load_venues`: membaca data lalu mengubahnya ke UTM (meter).
- `spatial_join`: menyisakan tempat yang berada di dalam batas CitraLand.
- `filter_by_sport`: menyaring berdasarkan olahraga.
- `rank_by_distance`: mengurutkan tempat berdasarkan jarak garis lurus.
- `get_graph`: memuat jaringan jalan.
- `_route`: menghitung rute terpendek antara dua titik.
- `route_to_nearest`: membandingkan rute ke beberapa kandidat teratas, lalu memilih yang terpendek.

Contoh mengubah: `network_type="drive"` di baris 83 bisa diganti `"walk"` untuk rute jalan kaki. Hapus `data/graph.graphml` setelahnya supaya jaringan diunduh ulang.

## `app.py`: penghubung

- Baris 13-14: memuat data sekali saat server menyala.
- `km_text`: memformat jarak, misalnya `1,25 km`.
- `resolve_origin`: menentukan titik awal, dengan cadangan kalau alamat gagal diproses.
- `build_map`: menggambar batas, marker, rute, dan legenda dengan Folium.
- `index`, baris 114: menerima request, memanggil fungsi lain, lalu mengirim hasilnya ke template.

Contoh mengubah: `radius=7` di baris 68 mengatur ukuran marker, dan `weight=5` di baris 86 mengatur tebal garis rute.

## Alur saat "Tampilkan Rute" diklik

1. `app.py` membaca `action`, `sport`, dan `address` dari URL.
2. `gis.py` menyisakan tempat di dalam batas, lalu memfilter olahraganya.
3. `data_fetch.geocode` mengubah alamat menjadi koordinat.
4. `gis.py` mengurutkan tempat, lalu menghitung rute ke 3 kandidat terdekat.
5. `build_map` menggambar hasilnya, lalu `index.html` menampilkannya.

## Latihan

Tambahkan olahraga Voli: tulis satu baris baru di `SPORTS` pada `config.py`. Kenapa dropdown dan legenda ikut berubah tanpa mengedit `index.html`, dan kenapa belum ada marker Voli di peta?
