-- =============================================================================
-- Justin
-- Trigger No. 2 - Validasi Venue
--   2.1 Mencegah Duplikasi Nama Venue di Kota yang Sama (ignore case)
--   2.2 Mencegah Penghapusan Venue jika Masih Memiliki Event Aktif
-- =============================================================================


-- ─── 2.1 TRIGGER: Cegah duplikasi venue di kota yang sama (case-insensitive) ─

CREATE OR REPLACE FUNCTION validate_venue_no_duplicate()
RETURNS TRIGGER AS $$
DECLARE
    v_existing venue%ROWTYPE;
BEGIN
    SELECT *
      INTO v_existing
      FROM venue
     WHERE LOWER(venue_name) = LOWER(NEW.venue_name)
       AND LOWER(city)       = LOWER(NEW.city)
       AND venue_id         <> NEW.venue_id;

    IF FOUND THEN
        RAISE EXCEPTION 'Venue "%" di kota "%" sudah terdaftar dengan ID %.',
            NEW.venue_name, NEW.city, v_existing.venue_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_venue_no_duplicate ON venue;

CREATE TRIGGER trg_validate_venue_no_duplicate
BEFORE INSERT OR UPDATE ON venue
FOR EACH ROW
EXECUTE FUNCTION validate_venue_no_duplicate();


-- ─── 2.2 TRIGGER: Cegah hapus venue yang masih punya event ──────────────────

CREATE OR REPLACE FUNCTION validate_venue_no_delete_with_events()
RETURNS TRIGGER AS $$
DECLARE
    v_event_count INTEGER;
BEGIN
    SELECT COUNT(*)
      INTO v_event_count
      FROM event
     WHERE venue_id = OLD.venue_id;

    IF v_event_count > 0 THEN
        RAISE EXCEPTION 'Venue "%" masih memiliki event aktif sehingga tidak dapat dihapus.',
            OLD.venue_name;
    END IF;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_venue_no_delete_with_events ON venue;

CREATE TRIGGER trg_validate_venue_no_delete_with_events
BEFORE DELETE ON venue
FOR EACH ROW
EXECUTE FUNCTION validate_venue_no_delete_with_events();
