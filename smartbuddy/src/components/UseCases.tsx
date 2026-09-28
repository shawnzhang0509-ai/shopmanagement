import Image from "next/image";
import Link from "next/link";
import { useCases } from "@/data/site";

export function UseCases() {
  return (
    <section
      id="use-cases"
      className="border-t border-stoneline bg-paper py-12 md:py-24"
      aria-labelledby="use-cases-heading"
    >
      <div className="mx-auto max-w-container px-4 sm:px-6 lg:px-8">
        <h2
          id="use-cases-heading"
          className="font-serif text-3xl text-ferndeep sm:text-4xl"
        >
          Use cases
        </h2>
        <div className="mt-10 grid gap-8 sm:grid-cols-2">
          {useCases.map((item) => (
            <article
              key={item.slug}
              className="overflow-hidden rounded-card border border-stoneline bg-mist"
            >
              <div className="relative aspect-[16/10] w-full">
                <Image
                  src={item.image}
                  alt=""
                  fill
                  className="object-cover"
                  sizes="(max-width: 768px) 100vw, 50vw"
                />
              </div>
              <div className="p-6">
                <h3 className="font-serif text-xl text-fern">{item.title}</h3>
                <p className="mt-2 font-serif text-lg text-ink/90">
                  &ldquo;{item.quote}&rdquo;
                </p>
                <ul className="mt-4 space-y-2 text-sm text-ink/80">
                  {item.bullets.map((bullet) => (
                    <li key={bullet} className="flex gap-2">
                      <span className="text-moss" aria-hidden>
                        —
                      </span>
                      {bullet}
                    </li>
                  ))}
                </ul>
                <Link
                  href="#get-smartbuddy"
                  className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-ocean transition-colors duration-300 hover:text-oceandeep"
                >
                  Learn more
                  <span aria-hidden>→</span>
                </Link>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
