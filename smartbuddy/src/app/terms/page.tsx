import Link from "next/link";

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-container px-4 py-24 sm:px-6 lg:px-8">
      <h1 className="font-serif text-3xl text-fern">Terms</h1>
      <p className="mt-4 text-ink/80">
        Terms of service placeholder — replace with legal copy before launch.
      </p>
      <Link href="/" className="mt-8 inline-block text-ocean hover:underline">
        Back to home
      </Link>
    </main>
  );
}
