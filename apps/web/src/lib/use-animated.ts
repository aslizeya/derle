"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * Reveal items one at a time. The pipeline answers in a fraction of a second; pacing its
 * real events makes each step readable without ever showing something that did not happen.
 */
export function usePacedCount(total: number, intervalMs = 170): number {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (reduce) return;
    if (shown >= total) return;
    const id = window.setTimeout(() => setShown((s) => s + 1), shown === 0 ? 0 : intervalMs);
    return () => window.clearTimeout(id);
  }, [shown, total, intervalMs, reduce]);
  return reduce ? total : shown;
}

/** Animate a number from its previous value to `target`. */
export function useCountUp(target: number, durationMs = 700): number {
  const reduce = useReducedMotion();
  const [value, setValue] = useState(reduce ? target : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduce) return;
    const start = performance.now();
    const origin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - p) ** 3;
      setValue(Math.round(origin + (target - origin) * eased));
      if (p < 1) frame = requestAnimationFrame(tick);
      else from.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, reduce]);
  return reduce ? target : value;
}
