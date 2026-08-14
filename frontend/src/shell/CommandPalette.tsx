/**
 * The ⌘K palette — porcelain's one glass object (register §3), and the "go to" shortcut
 * TOOLS §3 asks for once a system has more than a handful of screens. Atlas has 150+ routes
 * and had no global jump at all before this (CURRENT.md's absence sweep).
 *
 * Restraint is the design here: this is the only blurred surface in the entire app. Nothing
 * structural blurs, and the panel is the only thing that ever floats.
 *
 * Pattern: `role="dialog"` containing a combobox — focus stays in the input and a virtual
 * `aria-activedescendant` selection moves with the arrows, so screen readers announce the
 * highlighted row without focus ever leaving the field.
 */

import { useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";

import { Icon, type IconName } from "@/components/Icon";
import { useMe } from "@/lib/session";
import { moduleLinkProps } from "@/shell/ModuleLink";
import { modulesFor } from "@/shell/moduleRegistry";

interface Command {
  id: string;
  label: string;
  hint: string;
  icon: IconName;
  run: () => void;
}

/** Cmd on Apple hardware, Ctrl everywhere else — checked once, at module load. */
const IS_APPLE =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const SHORTCUT_LABEL = IS_APPLE ? "⌘K" : "Ctrl K";

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const setOpen = onOpenChange;
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const invokerRef = useRef<Element | null>(null);
  const navigate = useNavigate();
  const me = useMe();
  const modules = modulesFor(me.data?.permissions ?? []);

  // Global shortcut. Bound on the window so it works from anywhere, including inside a
  // module page's own inputs.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        invokerRef.current = document.activeElement;
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      inputRef.current?.focus();
    } else if (invokerRef.current instanceof HTMLElement) {
      // Focus returns where it came from, per the modal contract.
      invokerRef.current.focus();
    }
  }, [open]);

  const commands = useMemo<Command[]>(
    () => [
      {
        id: "home",
        label: "Go to Home",
        hint: "Overview",
        icon: "home",
        run: () => void navigate({ to: "/" }),
      },
      ...modules.map((entry) => ({
        id: `module-${entry.key}`,
        label: `Go to ${entry.label}`,
        hint: entry.description,
        icon: entry.icon,
        run: () => void navigate(moduleLinkProps(entry)),
      })),
    ],
    [modules, navigate],
  );

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter(
      (command) =>
        command.label.toLowerCase().includes(needle) || command.hint.toLowerCase().includes(needle),
    );
  }, [commands, query]);

  const clampedActive = Math.min(active, Math.max(matches.length - 1, 0));

  const choose = (command: Command | undefined) => {
    if (!command) return;
    setOpen(false);
    command.run();
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((previous) => (matches.length === 0 ? 0 : (previous + 1) % matches.length));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((previous) =>
        matches.length === 0 ? 0 : (previous - 1 + matches.length) % matches.length,
      );
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      choose(matches[clampedActive]);
      return;
    }
    // Focus is trapped: the palette is a combobox, so Tab has nowhere useful to go.
    if (event.key === "Tab") event.preventDefault();
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[18vh]"
      // Clicking the backdrop dismisses; the panel stops the event so clicks inside don't.
      onMouseDown={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
        className="glass-panel glass-panel-enter w-full max-w-[420px] p-2.5"
      >
        {/* The input carries its own opaque fill: secondary text is not legible directly on
            glass (measured 3.98:1), so anything muted needs a backing. */}
        <div className="mb-1 flex h-11 items-center gap-2.5 rounded-[10px] border border-line bg-surface px-3">
          <span className="text-ink-muted">
            <Icon name="search" size={15} />
          </span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            role="combobox"
            aria-expanded="true"
            aria-controls="atlas-palette-list"
            aria-autocomplete="list"
            {...(matches[clampedActive]
              ? { "aria-activedescendant": `atlas-palette-${matches[clampedActive].id}` }
              : {})}
            placeholder="Search or jump to…"
            className="h-full flex-1 bg-transparent text-[13.5px] text-ink outline-none placeholder:text-ink-muted"
          />
          <kbd className="kbd">{SHORTCUT_LABEL}</kbd>
        </div>

        <ul id="atlas-palette-list" role="listbox" aria-label="Commands" className="max-h-[320px] overflow-y-auto">
          {matches.length === 0 && (
            <li className="px-3 py-6 text-center text-[13px] text-ink">
              Nothing matches “{query}”.
            </li>
          )}
          {matches.map((command, index) => (
            <li
              key={command.id}
              id={`atlas-palette-${command.id}`}
              role="option"
              aria-selected={index === clampedActive}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(command)}
              className={`flex h-11 cursor-pointer items-center gap-3 rounded-[10px] px-3 text-[13.5px] text-ink ${
                index === clampedActive ? "glass-row-active" : ""
              }`}
            >
              <Icon name={command.icon} size={15} />
              {command.label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
