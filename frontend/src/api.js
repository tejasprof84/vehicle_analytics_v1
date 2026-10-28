// Thin wrappers around the FastAPI endpoints.
const get = async (path) => {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
};

export const fetchSummary = (minutes) => get(`/api/summary?minutes=${minutes}`);
export const fetchEvents = (limit = 25) => get(`/api/events?limit=${limit}`);
export const fetchTimeseries = (minutes) => get(`/api/timeseries?minutes=${minutes}`);

// Annotated video (HLS) published by MediaMTX, passed through the API's /hls route
// so it comes from the same origin as the dashboard. Override with VITE_HLS_URL at build time.
export const HLS_URL = import.meta.env.VITE_HLS_URL || "/hls/processed/index.m3u8";
