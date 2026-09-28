import Link from "next/link";
import { navLinks } from "@/data/site";

export function Footer() {
  return (
    <footer className="border-t border-ocean/30 bg-night py-12 text-paper/75">
      <div className="mx-auto max-w-container px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-8 md:flex-row md:justify-between">
          <div>
            <p className="font-serif text-lg text-paper">SmartBuddy</p>
            <p className="mt-2 max-w-sm text-sm">
              Kia ora — your buddy for the good life.
            </p>
            <p className="mt-4 text-xs text-paper/55">
              Made in Aotearoa New Zealand
            </p>
          </div>
          <nav aria-label="Footer">
            <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              {navLinks.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="transition-colors duration-300 hover:text-paper"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
              <li>
                <Link href="/privacy" className="hover:text-paper">
                  Privacy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="hover:text-paper">
                  Terms
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </footer>
  );
}
