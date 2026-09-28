import { trustPoints } from "@/data/site";

export function Trust() {
  return (
    <section
      className="bg-oceandeep py-12 text-paper md:py-24"
      aria-labelledby="trust-heading"
    >
      <div className="mx-auto max-w-container px-4 sm:px-6 lg:px-8">
        <h2
          id="trust-heading"
          className="max-w-xl font-serif text-3xl sm:text-4xl"
        >
          Your data stays in New Zealand.
        </h2>
        <p className="mt-4 max-w-2xl text-paper/80">
          SmartBuddy is built for trust first — the same bar you expect from
          your bank, not a social app.
        </p>
        <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {trustPoints.map((point) => (
            <li
              key={point}
              className="rounded-card border border-ocean/60 bg-night/40 px-5 py-4 text-sm leading-relaxed"
            >
              {point}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
