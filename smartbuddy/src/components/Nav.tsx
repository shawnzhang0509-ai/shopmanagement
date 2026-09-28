"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { navLinks } from "@/data/site";
import { PrimaryCta } from "./PrimaryCta";

export function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 border-b transition-colors duration-300 ${
        scrolled
          ? "border-stoneline/80 bg-mist/80 backdrop-blur-md"
          : "border-transparent bg-mist/80 backdrop-blur-md"
      }`}
    >
      <nav
        className="mx-auto flex max-w-container items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8"
        aria-label="Main"
      >
        <Link
          href="/"
          className="font-serif text-lg text-fern transition-opacity duration-300 hover:opacity-80"
        >
          SmartBuddy
        </Link>
        <ul className="hidden items-center gap-6 md:flex">
          {navLinks.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="text-sm text-ink/80 transition-colors duration-300 hover:text-fern"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
        <PrimaryCta className="shrink-0 text-sm" />
      </nav>
    </header>
  );
}
