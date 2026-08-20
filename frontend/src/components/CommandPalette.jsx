import { useEffect, useMemo, useState } from "react";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command";
import { buildPaletteEntries } from "../config/navigationConfig";

/** Command Palette (Ctrl+K / Cmd+K) — lompat cepat ke menu mana pun sesuai role. */
export const CommandPalette = ({ role, onNavigate }) => {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onOpenEvent = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("kn-open-palette", onOpenEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("kn-open-palette", onOpenEvent);
    };
  }, []);

  const groups = useMemo(() => {
    const entries = buildPaletteEntries(role || "sales");
    const byGroup = {};
    entries.forEach((e) => { (byGroup[e.group] = byGroup[e.group] || []).push(e); });
    return Object.entries(byGroup);
  }, [role]);

  const go = (entry) => {
    setOpen(false);
    onNavigate(entry.navId, entry.view, entry.tab);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput data-testid="command-palette-input" placeholder="Cari menu… (mis. 'pajak', 'payroll', 'retur')" />
      <CommandList data-testid="command-palette-list">
        <CommandEmpty>Menu tidak ditemukan.</CommandEmpty>
        {groups.map(([group, items]) => (
          <CommandGroup key={group} heading={group}>
            {items.map((e) => {
              const Icon = e.icon;
              return (
                <CommandItem
                  key={`${e.view}-${e.tab || ""}`}
                  value={`${group} ${e.label}`}
                  data-testid={`palette-item-${e.view}${e.tab ? `-${e.tab}` : ""}`}
                  onSelect={() => go(e)}
                >
                  {Icon ? <Icon size={14} className="mr-2 opacity-70" /> : null}
                  <span>{e.label}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
};

export default CommandPalette;
