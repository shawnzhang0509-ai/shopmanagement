"use client";

import { useState } from "react";
import { faqItems } from "@/data/site";

export function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <section
      id="faq"
      className="border-t border-ocean/30 bg-night py-12 text-paper md:py-24"
      aria-labelledby="faq-heading"
    >
      <div className="mx-auto max-w-container px-4 sm:px-6 lg:px-8">
        <h2 id="faq-heading" className="font-serif text-3xl sm:text-4xl">
          FAQ
        </h2>
        <div className="mt-10 divide-y divide-ocean/40 border-y border-ocean/40">
          {faqItems.map((item, index) => {
            const open = openIndex === index;
            const panelId = `faq-panel-${index}`;
            const buttonId = `faq-button-${index}`;
            return (
              <div key={item.question}>
                <h3>
                  <button
                    id={buttonId}
                    type="button"
                    className="flex w-full items-center justify-between gap-4 py-5 text-left text-base font-medium transition-colors duration-300 hover:text-moss"
                    aria-expanded={open}
                    aria-controls={panelId}
                    onClick={() => setOpenIndex(open ? null : index)}
                  >
                    {item.question}
                    <span
                      className="shrink-0 text-moss transition-transform duration-300"
                      aria-hidden
                      style={{ transform: open ? "rotate(45deg)" : undefined }}
                    >
                      +
                    </span>
                  </button>
                </h3>
                <div
                  id={panelId}
                  role="region"
                  aria-labelledby={buttonId}
                  hidden={!open}
                  className="pb-5 text-sm leading-relaxed text-paper/80"
                >
                  {item.answer}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
