# SmartBuddy.co.nz — marketing site

Single-page marketing site for SmartBuddy, built with Next.js 14 (App Router), TypeScript, Tailwind CSS, and framer-motion (hero parallax only).

## Develop

```bash
cd smartbuddy
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Production

```bash
npm run build
npm start
```

## Image & media shot list

Replace placeholder files under `public/images/` before launch. Budget targets:

| Asset | Path | Spec |
| --- | --- | --- |
| Hero bush (desktop) | `/images/hero-bush.webp` | Layered bush-morning, NZ forest; ~1600×900; used at ~55% opacity with mist gradient |
| Hero bush (mobile) | `/images/hero-bush-mobile.webp` | Static hero; **≤300KB** |
| Hero video poster | `/images/hero-poster.webp` | First frame for optional loop |
| Hero video loop (optional desktop) | `/images/hero-loop.mp4` | Subtle loop; **≤1.5MB**; add `<video>` in `Hero.tsx` when ready |
| Use case — tradies | `/images/use-case-tradies.webp` | Real NZ photography, tradie / van / site |
| Use case — parents | `/images/use-case-parents.webp` | Family / school morning, NZ |
| Use case — investors | `/images/use-case-investors.webp` | Home office / harbour city NZ |
| Use case — migrants | `/images/use-case-migrants.webp` | Welcoming urban NZ, diverse |
| How it works step 1 | `/images/step-1.png` | Product screenshot: connect services |
| How it works step 2 | `/images/step-2.png` | Diff / approval UI |
| How it works step 3 | `/images/step-3.png` | Proactive notification |
| Final CTA beach | `/images/final-beach.webp` | Evening beach, NZ coast; full-bleed dark overlay |

Placeholders in the repo are solid-colour exports for layout only.

## Brand

- **Light → dark journey:** mist/sand hero through ocean/night trust and pricing.
- **Fonts:** Fraunces (headings), Inter (body) via `next/font`.
- **Primary CTA copy:** only use **“Get your SmartBuddy”** (see `src/data/site.ts`).

## Structure

- `src/data/chats.ts` — hero preset Q&A (verbatim)
- `src/data/site.ts` — buddies, use cases, pricing, FAQ, nav
- `src/components/` — section components
- `src/app/page.tsx` — single-page assembly
