import Image from "next/image";
import { PrimaryCta } from "./PrimaryCta";

export function FinalCta() {
  return (
    <section
      id="get-smartbuddy"
      className="relative flex min-h-[420px] items-center justify-center py-24"
      aria-labelledby="final-cta-heading"
    >
      <Image
        src="/images/final-beach.webp"
        alt=""
        fill
        className="object-cover"
        sizes="100vw"
      />
      <div className="absolute inset-0 bg-oceandeep/75" aria-hidden />
      <div className="relative z-10 mx-auto max-w-container px-4 text-center sm:px-6 lg:px-8">
        <h2
          id="final-cta-heading"
          className="font-serif text-3xl text-paper sm:text-4xl md:text-5xl"
        >
          It remembers your world. You just live your life.
        </h2>
        <PrimaryCta variant="dark" className="mt-10" />
      </div>
    </section>
  );
}
