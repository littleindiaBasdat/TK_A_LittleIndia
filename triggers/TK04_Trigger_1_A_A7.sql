-- =============================================================================
-- Kelompok
-- Trigger No. 1 - Validasi Registrasi Pengguna [WAJIB]
--   1.1 Pengecekan Username (case-insensitive uniqueness)
--   1.2 Mencegah Username dengan Karakter Spesial (hanya a-z, A-Z, 0-9)
-- Fires: BEFORE INSERT OR UPDATE ON user_account
-- =============================================================================

CREATE OR REPLACE FUNCTION validate_user_registration()
RETURNS TRIGGER AS $$
DECLARE
    v_existing user_account%ROWTYPE;
BEGIN
    -- Username hanya boleh huruf dan angka (NO spasi/simbol)
    -- Dicek duluan supaya pesan special-char muncul untuk input yg memang invalid baru cek uniqueness.
    IF NEW.username !~ '^[a-zA-Z0-9]+$' THEN
        RAISE EXCEPTION 'ERROR: Username "%" hanya boleh mengandung huruf dan angka tanpa simbol atau spasi.',
            NEW.username;
    END IF;

    -- Username unik (case-insensitive)
    SELECT *
      INTO v_existing
      FROM user_account
     WHERE LOWER(username) = LOWER(NEW.username)
       AND user_id <> NEW.user_id;  -- exclude row itu sendiri penting untuk UPDATE

    IF FOUND THEN
        RAISE EXCEPTION 'ERROR: Username "%" sudah terdaftar, gunakan username lain.',
            NEW.username;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- TRIGGER: trg_validate_user_registration
DROP TRIGGER IF EXISTS trg_validate_user_registration ON user_account;

CREATE TRIGGER trg_validate_user_registration
BEFORE INSERT OR UPDATE OF username ON user_account
FOR EACH ROW
EXECUTE FUNCTION validate_user_registration();
