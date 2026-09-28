import type { Metadata } from "next";
import { Fraunces, Inter } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-fraunces",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SmartBuddy — Your AI buddy for life in New Zealand",
  description:
    "SmartBuddy remembers your world and acts on it: tax, family schedules, tickets and money — made for New Zealand, your data stays here.",
  openGraph: {
    title: "SmartBuddy — Your AI buddy for life in New Zealand",
    description:
      "SmartBuddy remembers your world and acts on it: tax, family schedules, tickets and money — made for New Zealand, your data stays here.",
    locale: "en_NZ",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-NZ" className={`${fraunces.variable} ${inter.variable}`}>
      <body>{children}</body>
    </html>
  );
}
