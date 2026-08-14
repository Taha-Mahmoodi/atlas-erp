/**
 * Light / dark / system, as a three-way segmented control rather than a two-way switch —
 * "system" is a real preference (follow the OS, keep following it), not the absence of one,
 * and a binary toggle silently discards it the first time you touch it.
 */

import { Icon, type IconName } from "@/components/Icon";
import { setTheme, useTheme, type ThemePreference } from "@/lib/theme";

const OPTIONS: { value: ThemePreference; icon: IconName; label: string }[] = [
  { value: "light", icon: "sun", label: "Light" },
  { value: "dark", icon: "moon", label: "Dark" },
  { value: "system", icon: "monitor", label: "Match system" },
];

export function ThemeToggle() {
  const preference = useTheme();

  return (
    <div role="group" aria-label="Theme" className="flex items-center gap-0.5 rounded-[8px] bg-panel p-0.5">
      {OPTIONS.map((option) => {
        const selected = preference === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setTheme(option.value)}
            aria-pressed={selected}
            title={option.label}
            className={`flex size-7 items-center justify-center rounded-[6px] transition-colors duration-150 ${
              selected ? "bg-surface text-ink shadow-card" : "text-ink-muted hover:text-ink"
            }`}
          >
            <Icon name={option.icon} size={14} />
            <span className="sr-only">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
