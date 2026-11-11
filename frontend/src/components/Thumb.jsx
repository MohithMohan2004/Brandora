import { useEffect, useState } from "react";
import { isApp } from "../api.js";

// Poster thumbnail. In the browser a plain <img> works. Inside the Android app the
// page is https and the server is plain http on the local network, and the WebView
// silently upgrades http <img> requests to https (which the server can't answer),
// so the image is fetched as data and shown from a blob URL instead.
export default function Thumb({ src, alt = "" }) {
  const [url, setUrl] = useState(isApp ? "" : src);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!isApp) { setUrl(src); return; }
    let live = true;
    let objectUrl = "";
    setFailed(false);
    fetch(src)
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((blob) => {
        if (!live) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  if (failed) return <span className="thumb-fallback" aria-hidden="true" />;
  if (!url) return <span className="thumb-loading" aria-hidden="true" />;
  return <img src={url} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} />;
}
