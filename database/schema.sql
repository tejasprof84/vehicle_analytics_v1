-- ---------------------------------------------------------------------------
-- Vehicle analytics schema (PostgreSQL)
--
-- One row = one line-crossing event of one tracked vehicle.
-- The DeepStream probe inserts rows; the dashboard API only reads them.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vehicle_events (
    id               BIGSERIAL PRIMARY KEY,
    vehicle_id       BIGINT      NOT NULL,                 -- tracker ID (unique per stream)
    vehicle_class    TEXT        NOT NULL DEFAULT 'car',   -- label from the primary detector
    color            TEXT        NOT NULL DEFAULT 'unknown', -- label from the secondary classifier
    color_confidence REAL,                                 -- classifier probability (0..1)
    direction        TEXT        NOT NULL,                 -- 'in' or 'out'
    line_name        TEXT,                                 -- nvdsanalytics line label
    source_id        INTEGER     NOT NULL DEFAULT 0,       -- stream index (multi-camera ready)
    frame_number     BIGINT,                               -- frame in which the crossing happened
    bbox_left        REAL,
    bbox_top         REAL,
    bbox_width       REAL,
    bbox_height      REAL,
    event_time       TIMESTAMPTZ NOT NULL DEFAULT now()    -- precise wall-clock time (UTC, microseconds)
);

-- Dashboard queries filter / group by time, colour and direction.
CREATE INDEX IF NOT EXISTS idx_vehicle_events_time      ON vehicle_events (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_color     ON vehicle_events (color);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_direction ON vehicle_events (direction);
