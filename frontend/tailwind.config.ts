import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f7f8f5",
        ink: "#18201c",
        muted: "#5d665e",
        panel: "#ffffff",
        line: "#d8ddd2",
        forest: "#1f6f50",
        cobalt: "#315d9d",
        amber: "#b97713",
        rose: "#b33a3a",
      },
      boxShadow: {
        surface: "0 1px 2px rgba(24, 32, 28, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
