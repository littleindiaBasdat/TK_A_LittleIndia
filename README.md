# Tugas Kelompok 3 (TK03) - TikTakTuk
**Implementasi UI – SQL DDL & Frontend**

---

##  Pembagian Tugas Tim
Berikut adalah daftar penanggung jawab untuk masing-masing fitur berdasarkan kesepakatan kelompok:

| Nama | Fitur & Tanggung Jawab |
| :--- | :--- |
| **Ammar** | Navbar (Semua), CUD Artist (Admin), R Artist (Semua), CUD Ticket Category (Admin/Org), R Ticket Category (Semua) |
| **Justin** | R Dashboard (Semua), C Tiket (Admin/Org), R Tiket (Semua), UD Tiket (Admin), CUD Seat (Admin/Org), R Seat (Semua) |
| **Abid** | C Pengguna (Semua), C Order (Customer), R Order (Semua), UD Order (Admin), CUD Promotion (Admin), R Promotion (Semua) |
| **Randra** | R Login/Logout (Semua), CUD Venue (Admin/Org), R Venue (Semua), CU Event (Admin/Org), R Event (Semua) |

---

##  Skenario & Deskripsi Fitur

### 1. Spesifikasi Navbar
Navbar bersifat dinamis sesuai status login pengguna:
*   **Guest:** Login, Registrasi.
*   **Admin:** Dashboard, Manajemen Venue, Kursi, Kategori Tiket, Tiket, Order, Aset, Profile.
*   **Organizer:** Dashboard, Event Saya, Manajemen Venue, Kursi, Kategori Tiket, Tiket, Order, Aset, Profile.
*   **Customer:** Dashboard, Tiket Saya, Pesanan, Cari Event, Promosi, Venue, Artis, Logout.

### 2. Autentikasi & Akun
*   **C - Pengguna (Register):** Pendaftaran sebagai Organizer, Customer, atau Admin dengan validasi field wajib.
*   **R - Login & Logout:** Sistem memvalidasi email/password, menyimpan session, dan mengarahkan ke dashboard profil sesuai role.

### 3. Profil & Dashboard
*   **RU - Dashboard:** Menampilkan informasi profil pengguna.
    *   Customer dapat mengubah nama dan nomor telepon.
    *   Organizer dapat mengubah nama organizer dan email kontak.
    *   Username bersifat permanen (tidak dapat diubah).
*   **Update Password:** Form khusus untuk mengganti kata sandi dengan validasi input.

### 4. Manajemen Event & Venue
*   **CUD Venue:** Pengelolaan lokasi acara meliputi Nama, Alamat, Kota, Kapasitas, dan jenis seating (Reserved/Free).
*   **CU Event:** Admin/Organizer membuat dan mengedit acara dengan detail Judul, Tanggal, Venue, Artis, dan Deskripsi.
*   **R Event:** Daftar acara ditampilkan dalam bentuk kartu (card) dengan fitur filter berdasarkan venue/artist.

### 5. Tiket & Tempat Duduk
*   **CUD Ticket Category:** Pengaturan kategori (VIP/Reguler), harga, dan kuota per event.
*   **CUD Seat:** Manajemen kursi untuk venue dengan "Reserved Seating". Kursi yang sudah terisi (Terisi) tidak bisa dihapus.
*   **CUD Tiket:** Admin/Organizer mencetak tiket berdasarkan Order ID dan kategori tertentu.

### 6. Transaksi & Promosi
*   **C Order:** Customer melakukan pembelian tiket, memilih kursi, dan menerapkan kode promo (opsional).
*   **CUD Promotion:** Admin mengelola kode promo, tipe diskon (persentase/nominal), dan batas penggunaan.
*   **R Order:** Ringkasan statistik order (Total, Lunas, Pending) dan riwayat transaksi sesuai hak akses role.
