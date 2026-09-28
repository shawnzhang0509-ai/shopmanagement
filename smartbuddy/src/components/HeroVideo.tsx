"use client";

import { useEffect, useState } from "react";

/** Optional desktop loop — add public/images/hero-loop.mp4 (≤1.5MB) + poster. */
export function HeroVideo() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(max-width: 767px)").matches) return;
    fetch("/images/hero-loop.mp4", { method: "HEAD" })
      .then((res) => setShow(res.ok))
      .catch(() => setShow(false));
  }, []);

  if (!show) return null;

  return (
    <video
      className="absolute inset-0 h-full w-full object-cover opacity-[0.55]"
      autoPlay
      muted
      loop
      playsInline
      poster="/images/hero-poster.webp"
      aria-hidden
    >
      <source src="/images/hero-loop.mp4" type="video/mp4" />
    </video>
  );
}
