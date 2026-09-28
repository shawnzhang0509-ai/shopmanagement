"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { chatPresets } from "@/data/chats";

type Props = {
  readOnly?: boolean;
};

export function HeroChat({ readOnly = false }: Props) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [displayText, setDisplayText] = useState("");
  const [typing, setTyping] = useState(false);
  const timerRef = useRef<number | null>(null);
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const playReply = useCallback(
    (text: string) => {
      clearTimer();
      if (readOnly || reduceMotion) {
        setDisplayText(text);
        setTyping(false);
        return;
      }
      setTyping(true);
      setDisplayText("");
      let i = 0;
      timerRef.current = window.setInterval(() => {
        i += 1;
        setDisplayText(text.slice(0, i));
        if (i >= text.length) {
          clearTimer();
          setTyping(false);
        }
      }, 18);
    },
    [readOnly, reduceMotion],
  );

  useEffect(() => () => clearTimer(), []);

  const onChip = (id: string, reply: string) => {
    if (readOnly) return;
    setActiveId(id);
    playReply(reply);
  };

  const preview = chatPresets[0];

  return (
    <div className="w-full max-w-xl rounded-card border border-stoneline bg-paper/95 p-5 shadow-lg shadow-fern/5 backdrop-blur-sm sm:p-6">
      <label htmlFor="hero-chat-input" className="sr-only">
        Ask your SmartBuddy
      </label>
      <input
        id="hero-chat-input"
        type="text"
        readOnly
        placeholder="Ask your SmartBuddy…"
        className="mb-4 w-full rounded-full border border-stoneline bg-mist px-4 py-3 text-sm text-ink placeholder:text-moss/80 focus:outline-none focus:ring-2 focus:ring-fern/30"
        aria-disabled={readOnly}
      />
      <div
        className="mb-4 flex flex-wrap gap-2"
        role={readOnly ? "presentation" : "group"}
        aria-label="Example prompts"
      >
        {chatPresets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            disabled={readOnly}
            onClick={() => onChip(preset.id, preset.reply)}
            className={`rounded-full border px-3 py-1.5 text-left text-xs transition-colors duration-300 sm:text-sm ${
              activeId === preset.id
                ? "border-fern bg-fern/10 text-fern"
                : "border-stoneline bg-sand/50 text-ink/90 hover:border-moss hover:bg-sand"
            } ${readOnly ? "cursor-default opacity-90" : ""}`}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <div
        className="min-h-[5.5rem] rounded-card border border-stoneline/80 bg-mist/80 px-4 py-3 text-sm leading-relaxed text-ink"
        aria-live="polite"
        aria-busy={typing}
      >
        {displayText ||
          (readOnly
            ? preview.reply
            : "Pick a prompt to see how SmartBuddy replies.")}
      </div>
    </div>
  );
}
