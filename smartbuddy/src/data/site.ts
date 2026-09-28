export const buddies = [
  {
    title: "Tax & Money Buddy",
    description:
      "Reads your bank feeds, tracks your GST, and reminds you before every IRD deadline.",
    tools: ["myIR", "ASB", "ANZ", "Xero"],
  },
  {
    title: "Family Ops Buddy",
    description:
      "Reads the school emails, builds the kids' week, and sends you a printable one-pager every Sunday.",
    tools: ["School email", "Calendar"],
  },
  {
    title: "Watchdog Buddy",
    description:
      "Watches tickets, prices and inboxes for the things you care about — and comes to you first.",
    tools: ["Trade Me", "Ticketek NZ", "Email"],
  },
] as const;

export const useCases = [
  {
    slug: "tradies",
    title: "For Tradies & the self-employed",
    quote: "Tax season without the shoebox of receipts.",
    image: "/images/use-case-tradies.webp",
    bullets: [
      "GST and expense categories from bank feeds",
      "IRD deadline reminders before penalties hit",
      "Draft returns you approve — nothing auto-filed",
    ],
  },
  {
    slug: "parents",
    title: "For Parents",
    quote: "Two schools' worth of emails, sorted before breakfast.",
    image: "/images/use-case-parents.webp",
    bullets: [
      "School newsletters parsed into a single week view",
      "Printable Sunday one-pager for the fridge",
      "Calendar holds without you copy-pasting",
    ],
  },
  {
    slug: "investors",
    title: "For Investors",
    quote: "A DCF in seconds. Watching so you don't have to.",
    image: "/images/use-case-investors.webp",
    bullets: [
      "Models and memos in plain language",
      "Price and news watchlists with alerts",
      "Every trade idea stays a draft until you say go",
    ],
  },
  {
    slug: "migrants",
    title: "For New migrants",
    quote: "IRD number, tax code, KiwiSaver — guided in plain English and 中文.",
    image: "/images/use-case-migrants.webp",
    bullets: [
      "Step-by-step for myIR and tax codes",
      "KiwiSaver and bank setup checklists",
      "Bilingual guidance when you need it",
    ],
  },
] as const;

export const howItWorksSteps = [
  {
    step: 1,
    title: "Tell it once",
    description:
      "Connect the services you use — banks, email, calendar — and tell SmartBuddy how you like things done.",
    image: "/images/step-1.png",
  },
  {
    step: 2,
    title: "It acts — you approve",
    description:
      "It prepares changes as a clear diff. You review, edit, and approve before anything runs.",
    image: "/images/step-2.png",
  },
  {
    step: 3,
    title: "It comes to you first",
    description:
      "Deadlines, tickets, and anomalies surface proactively — not buried in another inbox.",
    image: "/images/step-3.png",
  },
] as const;

export const trustPoints = [
  "NZ-hosted data",
  "Every action needs your approval",
  "Sandboxed execution",
  "Data never leaves the country",
  "RealMe verification (coming soon)",
] as const;

export const pricingTiers = [
  {
    name: "Free",
    price: "$0",
    period: "",
    description: "Limited daily tasks to try SmartBuddy on real life admin.",
    features: ["5 tasks per day", "One connected account", "Email support"],
    highlighted: false,
  },
  {
    name: "Buddy",
    price: "$19",
    period: "/mo",
    description: "Unlimited tasks + watchlists for one person who runs the household or business.",
    features: [
      "Unlimited tasks",
      "Watchlists (tickets, prices, inboxes)",
      "All NZ connectors",
      "Priority support",
    ],
    highlighted: true,
    badge: "unlimited tasks + watchlists",
  },
  {
    name: "Family or Trade",
    price: "$39",
    period: "/mo",
    description: "Multiple profiles for family members or tradie crew with separate contexts.",
    features: [
      "Up to 5 profiles",
      "Shared family calendar views",
      "Separate GST contexts",
      "Admin dashboard",
    ],
    highlighted: false,
  },
] as const;

export const faqItems = [
  {
    question: "Where does my data live?",
    answer:
      "On servers in New Zealand, encrypted. It never leaves the country — unlike overseas assistants.",
  },
  {
    question: "Can it act without asking me?",
    answer:
      "No. Every action shows you a diff and waits for your approval. Sensitive actions need a second confirmation.",
  },
  {
    question: "How is this different from ChatGPT or Meta's Muse?",
    answer:
      "They answer questions. SmartBuddy does the job — and it actually knows New Zealand: myIR, GST, KiwiSaver, Trade Me, school terms.",
  },
  {
    question: "What if it makes a mistake?",
    answer:
      "It prepares drafts — nothing is submitted to IRD or anyone else until you check and confirm it.",
  },
  {
    question: "Which NZ services does it connect to?",
    answer:
      "Banks (ASB, ANZ, Kiwibank), myIR, Trade Me, Ticketek NZ, Xero — with more added every month.",
  },
] as const;

export const navLinks = [
  { href: "#buddies", label: "The Buddies" },
  { href: "#use-cases", label: "Use cases" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#pricing", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
] as const;

export const PRIMARY_CTA_LABEL = "Get your SmartBuddy";
export const PRIMARY_CTA_HREF = "#get-smartbuddy";
