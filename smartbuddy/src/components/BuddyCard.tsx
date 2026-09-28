"use client";

import { useRef } from "react";

type Props = {
  title: string;
  description: string;
  tools: readonly string[];
};

export function BuddyCard({ title, description, tools }: Props) {
  const cardRef = useRef<HTMLElement>(null);

  const onMove = (e: React.MouseEvent<HTMLElement>) => {
    const el = cardRef.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    const rotateY = Math.max(-6, Math.min(6, x * 12));
    const rotateX = Math.max(-6, Math.min(6, -y * 12));
    el.style.transform = `perspective(900px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
  };

  const onLeave = () => {
    const el = cardRef.current;
    if (el) el.style.transform = "";
  };

  return (
    <article
      ref={cardRef}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      className="rounded-card border border-stoneline bg-paper p-6 shadow-sm transition-[transform,box-shadow] duration-300 will-change-transform hover:shadow-md"
      style={{ transformStyle: "preserve-3d" }}
    >
      <h3 className="font-serif text-xl text-fern">{title}</h3>
      <p className="mt-3 text-sm leading-relaxed text-ink/85">{description}</p>
      <p className="mt-4 text-xs font-medium uppercase tracking-wider text-moss">
        Tools
      </p>
      <p className="mt-1 text-sm text-ink/75">{tools.join(" · ")}</p>
    </article>
  );
}
