import { pricingTiers } from "@/data/site";
import { PrimaryCta } from "./PrimaryCta";

export function Pricing() {
  return (
    <section
      id="pricing"
      className="bg-night py-12 text-paper md:py-24"
      aria-labelledby="pricing-heading"
    >
      <div className="mx-auto max-w-container px-4 sm:px-6 lg:px-8">
        <h2
          id="pricing-heading"
          className="font-serif text-3xl sm:text-4xl"
        >
          Pricing
        </h2>
        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {pricingTiers.map((tier) => (
            <article
              key={tier.name}
              className={`flex flex-col rounded-card border p-6 ${
                tier.highlighted
                  ? "border-moss bg-oceandeep shadow-lg shadow-black/20"
                  : "border-ocean/50 bg-oceandeep/40"
              }`}
            >
              {tier.highlighted && "badge" in tier && (
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-moss">
                  {tier.badge}
                </p>
              )}
              <h3 className="font-serif text-xl">{tier.name}</h3>
              <p className="mt-3 tabular-nums">
                <span className="text-3xl font-medium">{tier.price}</span>
                <span className="text-paper/70">{tier.period}</span>
              </p>
              <p className="mt-3 text-sm text-paper/80">{tier.description}</p>
              <ul className="mt-6 flex-1 space-y-2 text-sm text-paper/85">
                {tier.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span className="text-moss" aria-hidden>
                      —
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
              <PrimaryCta
                variant="dark"
                className="mt-8 w-full"
              />
            </article>
          ))}
        </div>
        <p className="mt-10 text-center text-sm text-paper/65">
          An accountant typically charges $300–800/year for a GST return.
        </p>
      </div>
    </section>
  );
}
