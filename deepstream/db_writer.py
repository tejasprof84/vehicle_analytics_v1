"""
Asynchronous PostgreSQL writer for line-crossing events.

Why a background thread?
  The DeepStream probe runs inside the GStreamer streaming thread. If it waited
  for a database round-trip, every network hiccup would freeze the video.
  So the probe only does `queue.put_nowait(event)` (microseconds), and this
  thread drains the queue and inserts rows in small batches.

Guarantees:
  * never blocks the pipeline (queue full -> event dropped + warning)
  * batches inserts (fewer round-trips under heavy traffic)
  * reconnects automatically if PostgreSQL restarts
  * flushes remaining events on shutdown
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, astuple
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import execute_values

log = logging.getLogger("db_writer")

INSERT_SQL = """
    INSERT INTO vehicle_events
        (vehicle_id, vehicle_class, color, color_confidence, direction, line_name,
         source_id, frame_number, bbox_left, bbox_top, bbox_width, bbox_height, event_time)
    VALUES %s
"""


@dataclass
class VehicleEvent:
    """One vehicle crossing the counting line (field order = INSERT column order)."""
    vehicle_id: int
    vehicle_class: str
    color: str
    color_confidence: Optional[float]
    direction: str
    line_name: str
    source_id: int
    frame_number: int
    bbox_left: float
    bbox_top: float
    bbox_width: float
    bbox_height: float
    event_time: datetime


class DBWriter(threading.Thread):
    def __init__(self, dsn: str, batch_size: int = 50, flush_interval: float = 0.25,
                 max_queue: int = 10_000) -> None:
        super().__init__(name="db-writer", daemon=True)
        self.dsn = dsn
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.queue: "queue.Queue[VehicleEvent]" = queue.Queue(maxsize=max_queue)
        self._stop_event = threading.Event()
        self._conn = None
        self.inserted = 0
        self.dropped = 0

    # ---- called from the GStreamer probe (must be fast) -------------------
    def submit(self, event: VehicleEvent) -> None:
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1
            log.warning("DB queue full - dropped event for vehicle %s", event.vehicle_id)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self.join(timeout)

    # ---- background thread ------------------------------------------------
    def _connect(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._conn = psycopg2.connect(self.dsn)
                self._conn.autocommit = False
                log.info("Connected to PostgreSQL")
                return
            except psycopg2.OperationalError as exc:
                log.error("PostgreSQL not reachable (%s) - retrying in 2 s", exc)
                time.sleep(2)

    def _flush(self, batch: List[VehicleEvent]) -> bool:
        if not batch:
            return True
        try:
            if self._conn is None or self._conn.closed:
                self._connect()
                if self._conn is None:
                    return False
            with self._conn.cursor() as cur:
                execute_values(cur, INSERT_SQL, [astuple(e) for e in batch])
            self._conn.commit()
            self.inserted += len(batch)
            log.debug("Inserted %d events (total %d)", len(batch), self.inserted)
            return True
        except psycopg2.Error as exc:
            log.error("Insert failed (%s) - will retry", exc)
            try:
                self._conn.rollback()
            except Exception:  # connection already dead
                self._conn = None
            return False

    def run(self) -> None:
        self._connect()
        batch: List[VehicleEvent] = []
        last_flush = time.monotonic()

        while not (self._stop_event.is_set() and self.queue.empty()):
            try:
                batch.append(self.queue.get(timeout=self.flush_interval))
            except queue.Empty:
                pass

            due = time.monotonic() - last_flush >= self.flush_interval
            if batch and (len(batch) >= self.batch_size or due or self._stop_event.is_set()):
                if self._flush(batch):
                    batch = []
                else:
                    time.sleep(1)  # back off, keep the batch and retry
                last_flush = time.monotonic()

        self._flush(batch)  # final flush on shutdown
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        log.info("DB writer stopped (inserted=%d, dropped=%d)", self.inserted, self.dropped)
