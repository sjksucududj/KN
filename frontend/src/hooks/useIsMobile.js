import { useEffect, useState } from "react";

/**
 * F-6 — Deteksi viewport mobile (reaktif terhadap resize/rotasi).
 * Default breakpoint 768px (tablet-portrait ke bawah dianggap mobile).
 */
export default function useIsMobile(breakpoint = 768) {
  const query = `(max-width: ${breakpoint}px)`;
  const getMatch = () =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false;

  const [isMobile, setIsMobile] = useState(getMatch);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(query);
    const handler = (e) => setIsMobile(e.matches);
    setIsMobile(mq.matches);
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else mq.addListener(handler);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener("change", handler);
      else mq.removeListener(handler);
    };
  }, [query]);

  return isMobile;
}
