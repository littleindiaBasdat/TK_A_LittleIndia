-- =============================================================================
-- Abid
-- Trigger No. 5 - Validasi Kursi & Tiket
--   5.1 Memeriksa Keterikatan Kursi sebelum Menghapus Kursi
--   5.2 Memeriksa dan Memastikan Kuota Kategori Tiket saat Membuat Tiket
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Trigger 5.1 – Cegah hapus seat yang sudah di-assign ke tiket
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_check_seat_before_delete()
RETURNS TRIGGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM has_relationship
    WHERE seat_id = OLD.seat_id;

    IF v_count > 0 THEN
        RAISE EXCEPTION 'Kursi % - Baris % No. % tidak dapat dihapus karena sudah terisi.',
            OLD.section, OLD.row_number, OLD.seat_number;
    END IF;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_seat_before_delete ON seat;

CREATE TRIGGER trg_check_seat_before_delete
BEFORE DELETE ON seat
FOR EACH ROW
EXECUTE FUNCTION fn_check_seat_before_delete();


-- -----------------------------------------------------------------------------
-- Trigger 5.2 – Cegah insert ticket jika kuota kategori tiket sudah penuh
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fn_check_ticket_quota_before_insert()
RETURNS TRIGGER AS $$
DECLARE
    v_quota        INTEGER;
    v_name         VARCHAR;
    v_sold         INTEGER;
BEGIN
    SELECT quota, category_name
    INTO   v_quota, v_name
    FROM   ticket_category
    WHERE  category_id = NEW.category_id;

    SELECT COUNT(*)
    INTO   v_sold
    FROM   ticket
    WHERE  category_id = NEW.category_id;

    IF v_sold >= v_quota THEN
        RAISE EXCEPTION 'Kuota kategori tiket % sudah penuh. Tidak dapat membuat tiket baru.',
            v_name;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_ticket_quota_before_insert ON ticket;

CREATE TRIGGER trg_check_ticket_quota_before_insert
BEFORE INSERT ON ticket
FOR EACH ROW
EXECUTE FUNCTION fn_check_ticket_quota_before_insert();
