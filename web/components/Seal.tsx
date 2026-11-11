// 方章：姓名直書蓋在單據上。stamped=false 時是虛線的空白蓋章欄
export function Seal({ name, label, stamped, animate }: { name: string; label: string; stamped: boolean; animate?: boolean }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="grid size-16 place-items-center rounded-sm border border-dashed border-rule">
        {stamped && (
          <span
            className={`grid size-14 place-items-center rounded-[3px] border-2 border-seal font-display text-base leading-none font-bold text-seal opacity-90 ${animate ? "stamp-in" : "-rotate-[8deg]"}`}
            style={{ writingMode: "vertical-rl", letterSpacing: "0.05em" }}
            aria-label={`${label}：${name}`}
          >
            {name.slice(0, 4)}
          </span>
        )}
      </div>
      <span className="text-[11px] text-muted">{label}</span>
    </div>
  );
}
