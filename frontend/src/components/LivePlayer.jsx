import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { HLS_URL } from "../api.js";

// Plays the DeepStream-annotated stream that MediaMTX exposes as HLS.
// Retries automatically while the pipeline is starting up.
export default function LivePlayer() {
  const videoRef = useRef(null);
  const [state, setState] = useState("connecting");

  useEffect(() => {
    const video = videoRef.current;
    let hls = null;
    let retry = null;

    const start = () => {
      setState("connecting");
      if (Hls.isSupported()) {
        hls = new Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 });
        hls.loadSource(HLS_URL);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          setState("playing");
          video.play().catch(() => {});
        });
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (data.fatal) {
            setState("offline");
            hls.destroy();
            retry = setTimeout(start, 3000);
          }
        });
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = HLS_URL; // Safari plays HLS natively
        video
          .play()
          .then(() => setState("playing"))
          .catch(() => setState("offline"));
      }
    };

    start();
    return () => {
      clearTimeout(retry);
      hls?.destroy();
    };
  }, []);

  return (
    <div className="player">
      <video ref={videoRef} muted playsInline autoPlay />
      {state !== "playing" && (
        <div className="player-overlay">
          <span>
            {state === "connecting" ? "Connecting to stream…" : "Stream offline — retrying"}
          </span>
          <code>{HLS_URL}</code>
        </div>
      )}
    </div>
  );
}
