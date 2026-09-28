import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        mist: "#F7F5F0",
        sand: "#EFE9DF",
        paper: "#FCFBF8",
        fern: "#2E4A38",
        ferndeep: "#22382A",
        moss: "#6E8264",
        ocean: "#1E4D5C",
        oceandeep: "#0F2E38",
        night: "#121815",
        ink: "#1B211D",
        stoneline: "#E3DED4",
      },
      fontFamily: {
        serif: ["var(--font-fraunces)", "Georgia", "serif"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      maxWidth: {
        container: "72rem",
      },
      borderRadius: {
        card: "12px",
      },
      transitionDuration: {
        DEFAULT: "300ms",
      },
    },
  },
  plugins: [],
};
export default config;
