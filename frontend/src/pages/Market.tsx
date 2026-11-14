import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Search } from "lucide-react";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { api, type MarketOhlcResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const RANGES = ["3M", "6M", "1Y", "3Y"] as const;
type RangeKey = (typeof RANGES)[number];
const RANGE_DAYS: Record<RangeKey, number> = { "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095 };

const INTERVALS = ["1D", "1W", "1M"] as const;
type IntervalKey = (typeof INTERVALS)[number];

const QUICK_PICKS = ["000001.SZ", "600519.SH", "300750.SZ", "510300.SH", "00700.HK"] as const;

/** Local calendar day — `toISOString` would shift the date for UTC+8 mornings. */
function isoDay(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

export function Market() {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<string>("000001.SZ");
  const [symbol, setSymbol] = useState<string>("000001.SZ");
  const [range, setRange] = useState<RangeKey>("1Y");
  const [interval, setIntervalKey] = useState<IntervalKey>("1D");
  const [payload, setPayload] = useState<MarketOhlcResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(async (code: string, span: RangeKey, step: IntervalKey) => {
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) return;
    controller.current?.abort();
    const pending = new AbortController();
    controller.current = pending;
    setLoading(true);
    setError(null);
    try {
      const end = new Date();
      const start = new Date(end.getTime() - RANGE_DAYS[span] * 86_400_000);
      const result = await api.getMarketOhlc(
        trimmed,
        { start: isoDay(start), end: isoDay(end), interval: step },
        pending.signal,
      );
      if (pending.signal.aborted) return;
      setPayload(result);
    } catch (err) {
      if (pending.signal.aborted) return;
      setPayload(null);
      setError(err instanceof Error ? err.message : t("market.error"));
    } finally {
      if (!pending.signal.aborted) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load(symbol, range, interval);
  }, [symbol, range, interval, load]);

  useEffect(() => () => controller.current?.abort(), []);

  const bars = useMemo(() => payload?.bars ?? [], [payload]);
  const last = bars.length > 0 ? bars[bars.length - 1] : null;
  const previous = bars.length > 1 ? bars[bars.length - 2] : null;
  const changePct = last && previous && previous.close
    ? ((last.close - previous.close) / previous.close) * 100
    : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSymbol(draft.trim().toUpperCase());
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">{t("market.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("market.subtitle")}</p>
      </header>

      <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label={t("market.symbol")}
            placeholder={t("market.symbolPlaceholder")}
            spellCheck={false}
            className="w-56 rounded-lg border bg-background py-2 pe-3 ps-9 font-mono text-sm uppercase outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t("market.load")}
        </button>

        <div role="group" aria-label={t("market.range")} className="flex overflow-hidden rounded-lg border">
          {RANGES.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={range === item}
              onClick={() => setRange(item)}
              className={cn("px-3 py-2 text-xs", range === item ? "bg-primary text-primary-foreground" : "hover:bg-muted")}
            >
              {item}
            </button>
          ))}
        </div>

        <div role="group" aria-label={t("market.interval")} className="flex overflow-hidden rounded-lg border">
          {INTERVALS.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={interval === item}
              onClick={() => setIntervalKey(item)}
              className={cn("px-3 py-2 text-xs", interval === item ? "bg-primary text-primary-foreground" : "hover:bg-muted")}
            >
              {t(`market.interval_${item}`)}
            </button>
          ))}
        </div>
      </form>

      <div className="flex flex-wrap items-center gap-1.5">
        {QUICK_PICKS.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => { setDraft(code); setSymbol(code); }}
            className="rounded-full border px-2.5 py-1 font-mono text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {code}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
          {error}
        </div>
      )}

      {last && (
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <div className="font-mono text-lg font-semibold">{payload?.symbol}</div>
          <div className="text-3xl font-semibold tabular-nums">{last.close.toFixed(2)}</div>
          {changePct !== null && (
            <div className={cn("pb-1 text-sm font-medium tabular-nums", changePct >= 0 ? "text-success" : "text-danger")}>
              {changePct >= 0 ? "+" : ""}
              {changePct.toFixed(2)}%
            </div>
          )}
          <div className="ms-auto flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="rounded-full border px-2 py-0.5">{t("market.source")}: {payload?.source ?? "—"}</span>
            <span className="rounded-full border px-2 py-0.5">{t("market.caliber")}: {payload?.adjustment ?? "—"}</span>
            <span className="rounded-full border px-2 py-0.5">{bars.length} {t("market.bars")}</span>
            <span className="tabular-nums">{payload?.start} ~ {payload?.end}</span>
          </div>
        </div>
      )}

      <div className="rounded-xl border bg-card p-2">
        {bars.length > 0 ? (
          <CandlestickChart data={bars} height={520} />
        ) : (
          <div className="flex h-[520px] items-center justify-center text-sm text-muted-foreground">
            {loading ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : t("market.empty")}
          </div>
        )}
      </div>

      <p className="text-xs text-muted-foreground">{t("market.hint")}</p>
    </div>
  );
}
