# Deploy & Test Trigger No. 1 - Validasi Registrasi Pengguna [WAJIB]

## A. Deploy ke Railway PostgreSQL

### Cara 1: Via Railway Dashboard (Query Tab)
1. Buka https://railway.app/ dan login.
2. Pilih project yang berisi PostgreSQL service Anda.
3. Klik **PostgreSQL** service.
4. Tab **Data** → **Query**.
5. Buka file `TK04_Trigger_1_A_A7.sql`, copy SELURUH isinya.
6. Paste ke editor di Railway, klik **Run Query** (`Ctrl+Enter`).
7. Pastikan muncul: `CREATE FUNCTION`, `DROP TRIGGER` (kalau pertama kali bisa "trigger does not exist" - tidak apa-apa karena `IF EXISTS`), `CREATE TRIGGER`. Tidak boleh ada error merah.

### Cara 2: Via psql CLI
```powershell
psql "postgresql://postgres:WhQinPwISumUKjVSTrIUBZTwKpSirRtY@junction.proxy.rlwy.net:57133/railway" -f triggers/TK04_Trigger_1_A_A7.sql
```

## B. Verifikasi Trigger Terpasang

```sql
SELECT trigger_name, event_object_table, action_timing, event_manipulation
FROM information_schema.triggers
WHERE trigger_name = 'trg_validate_user_registration';
```
Harus mengembalikan 2 row (BEFORE INSERT + BEFORE UPDATE) dengan `event_object_table = 'user_account'`.

---

## C. Test 3 Skenario Trigger (Manual via SQL)

### Skenario 1: Username sudah terdaftar (case-insensitive) (1.1)
```sql
-- Ambil username yang sudah ada di DB:
SELECT user_id, username FROM user_account LIMIT 5;

-- Misal sudah ada "admin1", coba register dengan "ADMIN1":
INSERT INTO user_account (user_id, username, password)
VALUES (gen_random_uuid(), 'ADMIN1', 'hashed_password_dummy');

-- Hasil yang diharapkan:
-- ERROR: Username "ADMIN1" sudah terdaftar, gunakan username lain.
```

### Skenario 2: Username dengan karakter spesial (1.2)
```sql
-- Coba pakai spasi
INSERT INTO user_account (user_id, username, password)
VALUES (gen_random_uuid(), 'user @123', 'hashed_password_dummy');
-- Hasil yang diharapkan:
-- ERROR: Username "user @123" hanya boleh mengandung huruf dan angka tanpa simbol atau spasi.

-- Coba pakai simbol
INSERT INTO user_account (user_id, username, password)
VALUES (gen_random_uuid(), 'user#new', 'hashed_password_dummy');
-- Hasil yang diharapkan:
-- ERROR: Username "user#new" hanya boleh mengandung huruf dan angka tanpa simbol atau spasi.
```

### Skenario 3: Username valid (success case)
```sql
-- Username baru, hanya huruf dan angka
INSERT INTO user_account (user_id, username, password)
VALUES (gen_random_uuid(), 'testuser2026', 'hashed_password_dummy');

-- Hasil yang diharapkan: 1 row INSERT berhasil
-- Cleanup:
DELETE FROM user_account WHERE username = 'testuser2026';
```

---

## D. Test End-to-End via UI Django

1. Buka halaman **Register**
2. Pilih role apa saja (customer/organizer/admin)
3. **Test 1 (duplicate case-insensitive):**
   - Ketik username yang sudah ada di DB dengan huruf besar/kecil berbeda (misal `ADMIN1`)
   - Isi password & field wajib lainnya, klik **[Daftar]**
   - Banner merah harus muncul: `ERROR: Username "ADMIN1" sudah terdaftar, gunakan username lain.`
4. **Test 2 (karakter spesial):**
   - Ketik username dengan spasi atau simbol (misal `user @123`)
   - Klik **[Daftar]**
   - Banner merah: `ERROR: Username "user @123" hanya boleh mengandung huruf dan angka tanpa simbol atau spasi.`
5. **Test 3 (success):**
   - Username baru, alphanumeric only (misal `testuser2026`)
   - Klik **[Daftar]** → sukses, redirect ke login.

---

## E. Rollback (jika perlu)

```sql
DROP TRIGGER IF EXISTS trg_validate_user_registration ON user_account;
DROP FUNCTION IF EXISTS validate_user_registration();
```
