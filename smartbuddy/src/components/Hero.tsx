"use client";

import Image from "next/image";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { HeroChat } from "./HeroChat";
import { HeroVideo } from "./HeroVideo";

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const reduceMotion = useReducedMotion();
  const [isMobile, setIsMobile] = useState(true);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const parallaxY = useTransform(scrollYProgress, [0, 1], [0, 40]);
  const enableParallax = !isMobile && !reduceMotion;

  return (
    <section
      ref={ref}
      className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden pt-24 pb-12 md:pb-24"
      aria-labelledby="hero-heading"
    >
      <div className="pointer-events-none absolute inset-0">
        {enableParallax ? (
          <motion.div className="absolute inset-0" style={{ y: parallaxY }}>
            <HeroBackground isMobile={false} />
          </motion.div>
        ) : (
          <HeroBackground isMobile={isMobile} />
        )}
        <div
          className="absolute inset-0 bg-gradient-to-b from-mist/30 via-mist/70 to-mist"
          aria-hidden
        />
      </div>

      <div className="relative z-10 mx-auto flex max-w-container flex-col items-center px-4 text-center sm:px-6 lg:px-8">
        <p className="mb-3 text-sm font-medium tracking-wide text-moss">
          Your AI buddy, made for New Zealand
        </p>
        <h1
          id="hero-heading"
          className="max-w-3xl font-serif text-4xl leading-tight text-ferndeep sm:text-5xl lg:text-6xl"
        >
          More than answers, SmartBuddy acts.
        </h1>
        <p className="mt-4 max-w-2xl text-base text-ink/85 sm:text-lg">
          It remembers your world — your projects, your people, your preferences
          — and comes to you first.
        </p>
        <div className="mt-10 w-full flex justify-center">
          <HeroChat readOnly={isMobile} />
        </div>
      </div>
    </section>
  );
}

function HeroBackground({ isMobile }: { isMobile: boolean }) {
  const src = isMobile ? "/images/hero-bush-mobile.webp" : "/images/hero-bush.webp";

  return (
    <>
      {!isMobile && <HeroVideo />}
      <Image
        src={src}
        alt=""
        fill
        priority
        className="object-cover opacity-[0.55]"
        sizes="100vw"
      />
    </>
  );
}
