export type ChatPreset = {
  id: string;
  label: string;
  reply: string;
};

export const chatPresets: ChatPreset[] = [
  {
    id: "spending",
    label: "Sort my last two weeks of spending",
    reply:
      "Reviewed 41 card statements. Total $2,847. Two flags: Netflix $89 (duplicate sub on your old email), Uber Eats $124 at 2:37am Sunday. Cancel the old Netflix?",
  },
  {
    id: "tickets",
    label: "Watch for Taylor Swift NZ tickets",
    reply:
      "Watching Ticketek NZ, Live Nation NZ and official socials. I'll ping you the second a date or presale code drops. Price ceiling?",
  },
  {
    id: "kids",
    label: "What's on for the kids next week?",
    reply:
      "Emma (Y3): Mon 9am assembly, Wed museum trip (packed lunch), Fri teacher-only day. Jack (Y6): Thu geography test. Added to your calendar — want a printable one-pager?",
  },
  {
    id: "dcf",
    label: "Run a DCF on NVDA",
    reply:
      "Fair value ~$118 (WACC 10%, terminal growth 4%). Current $141 — I'd wait. Set an alert under $120?",
  },
  {
    id: "deck",
    label: "Fix client name to PURE across my deck",
    reply:
      "Found 23 instances across 8 slides, replaced all, skipped 2 in URLs. New file: pitch_v2.pptx, diff attached.",
  },
];
