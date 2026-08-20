/** Hub tab bar (Restrukturisasi IA) — navigasi sekunder antar-view dalam satu proses bisnis. */
export const HubTabs = ({ hubId, tabs, activeView, onSelect }) => {
  if (!tabs || tabs.length < 2) return null;
  return (
    <div data-testid={`hub-tabs-${hubId}`} className="flex flex-wrap items-center gap-1.5 mb-3 no-print">
      {tabs.map((t) => {
        const active = t.view === activeView;
        return (
          <button
            key={t.view}
            data-testid={`hub-tab-${t.view}`}
            onClick={() => onSelect(t.view, t.tab)}
            className={`px-3.5 py-1.5 rounded-full text-[12.5px] font-semibold border transition-colors ${
              active
                ? "bg-[#1C1C1E] text-white border-[#1C1C1E]"
                : "bg-white text-[#3A3A3C] border-[#E5E5EA] hover:border-[#1C1C1E]/40 hover:bg-[#F7F7F9]"
            }`}
            aria-current={active ? "page" : undefined}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
};

export default HubTabs;
