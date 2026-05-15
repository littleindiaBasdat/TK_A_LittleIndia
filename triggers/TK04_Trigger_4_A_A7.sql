-- =============================================================================
-- Fairuz Akhtar Randrasyah
-- Trigger No. 4 - Validasi Promotion
--   4.1 Validasi Promotion saat Digunakan ke sebuah Order
--   4.2 Validasi Promotion Berdasarkan Tanggal Event saat Digunakan ke Order
-- Fires: BEFORE INSERT ON order_promotion
-- =============================================================================


CREATE OR REPLACE FUNCTION validate_promotion_usage()
RETURNS TRIGGER AS $$
DECLARE
    v_promo       promotion%ROWTYPE;
    v_usage_count INTEGER;
    v_event_date  DATE;
BEGIN
    -- Promotion harus ada
    SELECT *
      INTO v_promo
      FROM promotion
     WHERE promotion_id = NEW.promotion_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'ERROR: Promotion dengan ID % tidak ditemukan.', NEW.promotion_id;
    END IF;

    -- Gaboleh lewatin usage limit
    SELECT COUNT(*)
      INTO v_usage_count
      FROM order_promotion
     WHERE promotion_id = NEW.promotion_id;

    IF v_usage_count >= v_promo.usage_limit THEN
        RAISE EXCEPTION 'ERROR: Promotion "%" telah mencapai batas maksimum penggunaan.',
            v_promo.promo_code;
    END IF;

    -- Event date harus berada dalam rentang promo
    SELECT DATE(e.event_datetime)
      INTO v_event_date
      FROM ticket t
      JOIN ticket_category tc ON t.category_id = tc.category_id
      JOIN event          e  ON tc.event_id    = e.event_id
     WHERE t.order_id = NEW.order_id
     LIMIT 1;

    -- Hanya cek tanggal jika tiket sudah ada untuk order tersebut
    -- Jika belum ada tiket, berarti event belum diketahui, jadi validasi tanggal tidak bisa dilakukan
    IF v_event_date IS NOT NULL THEN
        IF v_event_date < v_promo.start_date
           OR v_event_date > v_promo.end_date THEN
            RAISE EXCEPTION 'ERROR: Promotion "%" tidak berlaku untuk tanggal event ini.',
                v_promo.promo_code;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- TRIGGER: trg_validate_promotion_usage
DROP TRIGGER IF EXISTS trg_validate_promotion_usage ON order_promotion;

CREATE TRIGGER trg_validate_promotion_usage
BEFORE INSERT ON order_promotion
FOR EACH ROW
EXECUTE FUNCTION validate_promotion_usage();