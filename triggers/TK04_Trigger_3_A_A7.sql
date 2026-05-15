-- =============================================================================
-- Ammar
-- Trigger No. 3 - Validasi Artist & Kuota Tiket
--   3.1 Validasi Duplikasi (artist_id, event_id) pada EVENT_ARTIST
--   3.2 Menampilkan Sisa Kuota Ticket Category Berdasarkan event_id
-- =============================================================================


-- ─── 3.1 TRIGGER: Validasi INSERT pada event_artist ─────────────────────────

CREATE OR REPLACE FUNCTION validate_event_artist()
RETURNS TRIGGER AS $$
DECLARE
    v_artist_name   VARCHAR;
    v_event_title   VARCHAR;
BEGIN
    -- 1. Cek artist exist
    IF NOT EXISTS (SELECT 1 FROM artist WHERE artist_id = NEW.artist_id) THEN
        RAISE EXCEPTION 'Artist dengan ID % tidak ditemukan.', NEW.artist_id;
    END IF;

    -- 2. Cek event exist
    IF NOT EXISTS (SELECT 1 FROM event WHERE event_id = NEW.event_id) THEN
        RAISE EXCEPTION 'Event dengan ID % tidak ditemukan.', NEW.event_id;
    END IF;

    -- 3. Cek duplikasi (artist_id, event_id)
    IF EXISTS (
        SELECT 1 FROM event_artist
        WHERE event_id = NEW.event_id AND artist_id = NEW.artist_id
    ) THEN
        SELECT name INTO v_artist_name FROM artist WHERE artist_id = NEW.artist_id;
        SELECT event_title INTO v_event_title FROM event WHERE event_id = NEW.event_id;

        RAISE EXCEPTION 'Artist "%" sudah terdaftar pada event "%".', v_artist_name, v_event_title;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_event_artist ON event_artist;

CREATE TRIGGER trg_validate_event_artist
BEFORE INSERT ON event_artist
FOR EACH ROW EXECUTE FUNCTION validate_event_artist();


-- ─── 3.2 STORED FUNCTION: Sisa kuota tiket per event ───────────────────────

CREATE OR REPLACE FUNCTION get_remaining_quota_by_event(p_event_id UUID)
RETURNS TABLE (
    category_id     UUID,
    category_name   VARCHAR,
    quota           INTEGER,
    price           NUMERIC,
    tickets_sold    BIGINT,
    remaining       BIGINT
) AS $$
BEGIN
    -- 1. Cek event exist
    IF NOT EXISTS (SELECT 1 FROM event WHERE event_id = p_event_id) THEN
        RAISE EXCEPTION 'Event dengan ID % tidak ditemukan.', p_event_id;
    END IF;

    -- 2. Return kuota per ticket_category
    RETURN QUERY
        SELECT
            tc.category_id,
            tc.category_name,
            tc.quota,
            tc.price,
            COUNT(t.ticket_id)            AS tickets_sold,
            tc.quota - COUNT(t.ticket_id) AS remaining
        FROM ticket_category tc
        LEFT JOIN ticket t ON t.category_id = tc.category_id
        WHERE tc.event_id = p_event_id
        GROUP BY tc.category_id, tc.category_name, tc.quota, tc.price;
END;
$$ LANGUAGE plpgsql;