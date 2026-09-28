import Link from "next/link";
import { PRIMARY_CTA_HREF, PRIMARY_CTA_LABEL } from "@/data/site";

type Props = {
  className?: string;
  variant?: "light" | "dark";
};

export function PrimaryCta({ className = "", variant = "light" }: Props) {
  const base =
    "inline-flex items-center justify-center rounded-full px-6 py-3 text-sm font-medium transition-colors duration-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2";
  const styles =
    variant === "dark"
      ? "bg-paper text-ink hover:bg-mist focus-visible:outline-paper"
      : "bg-fern text-paper hover:bg-ferndeep focus-visible:outline-fern";

  return (
    <Link href={PRIMARY_CTA_HREF} className={`${base} ${styles} ${className}`}>
      {PRIMARY_CTA_LABEL}
    </Link>
  );
}
