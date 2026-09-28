import { buddies } from "@/data/site";
import { BuddyCard } from "./BuddyCard";

export function Buddies() {
  return (
    <section
      id="buddies"
      className="py-12 md:py-24"
      aria-labelledby="buddies-heading"
    >
      <div className="mx-auto max-w-container px-4 sm:px-6 lg:px-8">
        <h2
          id="buddies-heading"
          className="font-serif text-3xl text-ferndeep sm:text-4xl"
        >
          The Buddies
        </h2>
        <p className="mt-3 max-w-2xl text-ink/80">
          Three focused agents that know your context — not generic chatbots.
        </p>
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {buddies.map((buddy) => (
            <BuddyCard key={buddy.title} {...buddy} />
          ))}
        </div>
      </div>
    </section>
  );
}
