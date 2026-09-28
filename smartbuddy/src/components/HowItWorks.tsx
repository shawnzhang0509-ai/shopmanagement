import Image from "next/image";
import { howItWorksSteps } from "@/data/site";

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="bg-sand py-12 md:py-24"
      aria-labelledby="how-heading"
    >
      <div className="mx-auto max-w-container px-4 sm:px-6 lg:px-8">
        <h2
          id="how-heading"
          className="font-serif text-3xl text-ferndeep sm:text-4xl"
        >
          How it works
        </h2>
        <ol className="mt-12 space-y-16">
          {howItWorksSteps.map((step) => (
            <li
              key={step.step}
              className="grid items-center gap-8 md:grid-cols-2 md:gap-12"
            >
              <div className={step.step === 2 ? "md:order-2" : ""}>
                <p className="text-sm font-medium tabular-nums text-moss">
                  Step {step.step}
                </p>
                <h3 className="mt-2 font-serif text-2xl text-fern">
                  {step.title}
                </h3>
                <p className="mt-3 text-ink/85">{step.description}</p>
                {step.step === 2 && (
                  <div
                    className="mt-6 rounded-card border border-stoneline bg-paper p-4 text-left text-xs shadow-sm"
                    role="img"
                    aria-label="Example approval diff: rename client to PURE in presentation"
                  >
                    <p className="font-medium text-ink">Approve changes?</p>
                    <p className="mt-2 font-mono text-fern">
                      - Client: Acme Ltd
                      <br />
                      + Client: PURE
                    </p>
                    <p className="mt-2 text-moss">8 slides · 23 replacements</p>
                  </div>
                )}
              </div>
              <div
                className={`relative aspect-[4/3] overflow-hidden rounded-card border border-stoneline bg-paper ${
                  step.step === 2 ? "md:order-1" : ""
                }`}
              >
                <Image
                  src={step.image}
                  alt=""
                  fill
                  className="object-cover"
                  sizes="(max-width: 768px) 100vw, 50vw"
                />
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
