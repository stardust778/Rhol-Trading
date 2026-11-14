import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Loader2, Trash2, Upload } from "lucide-react";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import {
  api,
  type JournalAnalysis,
  type JournalBehaviorMetric,
  type JournalSummary,
  type JournalTrade,
  type MarketOhlcResponse,
  type TradeMarker,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const BEHAVIOR_ORDER = ["disposition_effect", "overtrading", "chasing_momentum", "anchoring"] as const;

/** Backend monetary metrics are scalars for one currency, maps when mixed. */
function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value && typeof value === "object") {
    const first = Object.values(value as Record<string, unknown>).find(
      (item): item is number => typeof item === "number" && Number.isFinite(item),
    );
    return first ?? null;
  }
  return null;
}

function fmtNumber(value: number | null, digits = 2): string {
  if (value === null) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function shiftDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function Journal() {
  const { t } = useTranslation();
  const fileInput = useRef<HTMLInputElement>(null);
  const [summary, setSummary] = useState<JournalSummary | null>(null);
  const [analysis, setAnalysis] = useState<JournalAnalysis | null>(null);
  const [trades, setTrades] = useState<JournalTrade[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [nextSummary, nextAnalysis, nextTrades] = await Promise.all([
        api.getJournalSummary(),
        api.getJournalAnalysis(),
        api.getJournalTrades(undefined, 200),
      ]);
      setSummary(nextSummary);
      setAnalysis(nextAnalysis);
      setTrades(nextTrades.trades);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("journal.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onFiles = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await api.uploadFile(file);
      const result = await api.importJournal(uploaded.file_path, uploaded.filename);
      toast.success(
        t("journal.importOk", { inserted: result.inserted, duplicates: result.duplicates }),
      );
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : t("journal.importFailed");
      setError(message);
      toast.error(message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const onDeleteImport = async (importId: string) => {
    try {
      await api.deleteJournalImport(importId);
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("journal.deleteFailed"));
    }
  };

  const profile = analysis?.profile;
  const behavior = analysis?.behavior;
  const months = analysis?.monthly_pnl ?? [];
  const topSymbols = useMemo(() => {
    const raw = profile?.top_symbols;
    return Array.isArray(raw) ? (raw as Array<{ symbol: string; trades: number; total_amount: number }>) : [];
  }, [profile]);

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  const hasRecords = (summary?.records ?? 0) > 0;

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <header className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">{t("journal.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("journal.subtitle")}</p>
        </div>
        <div className="ms-auto flex items-center gap-2">
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(event) => void onFiles(event.target.files)}
          />
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInput.current?.click()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
            {uploading ? t("journal.importing") : t("journal.importBtn")}
          </button>
        </div>
      </header>

      {error && (
        <div role="alert" className="rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
          {error}
        </div>
      )}

      {!hasRecords && (
        <div className="rounded-xl border border-dashed p-10 text-center">
          <Upload className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="mt-3 text-base font-medium">{t("journal.empty")}</p>
          <p className="mx-auto mt-1 max-w-xl text-sm text-muted-foreground">{t("journal.emptyHint")}</p>
          <p className="mt-4 text-xs text-muted-foreground">{t("journal.formats")}</p>
        </div>
      )}

      {hasRecords && summary && (
        <p className="text-xs text-muted-foreground">
          {summary.records} {t("journal.trades")} · {summary.symbols} {t("journal.symbols")} ·{" "}
          {summary.first_date?.slice(0, 10)} ~ {summary.last_date?.slice(0, 10)}
        </p>
      )}

      {hasRecords && profile && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <StatCard label={t("journal.totalPnl")} value={fmtNumber(asNumber(profile.total_pnl))} tone={asNumber(profile.total_pnl) ?? 0} />
          <StatCard label={t("journal.winRate")} value={profile.win_rate === undefined ? "—" : `${((asNumber(profile.win_rate) ?? 0) * 100).toFixed(1)}%`} />
          <StatCard label={t("journal.pnlRatio")} value={fmtNumber(asNumber(profile.profit_loss_ratio))} />
          <StatCard label={t("journal.avgHold")} value={`${fmtNumber(asNumber(profile.avg_holding_days), 1)} ${t("journal.days")}`} />
          <StatCard label={t("journal.frequency")} value={`${fmtNumber(asNumber(profile.trade_frequency_per_week), 2)} / ${t("journal.week")}`} />
          <StatCard label={t("journal.maxDrawdown")} value={fmtNumber(asNumber(profile.max_drawdown))} tone={asNumber(profile.max_drawdown) ?? 0} />
        </section>
      )}

      {hasRecords && behavior && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">{t("journal.behavior")}</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {BEHAVIOR_ORDER.map((key) => {
              const metric = behavior[key];
              if (!metric) return null;
              return <BehaviorCard key={key} title={t(`journal.${key}`)} metric={metric} />;
            })}
          </div>
        </section>
      )}

      {hasRecords && months.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">{t("journal.monthly")}</h2>
          <div className="rounded-xl border bg-card p-4">
            <MonthlyBars months={months} />
          </div>
        </section>
      )}

      {hasRecords && topSymbols.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">{t("journal.topSymbols")}</h2>
          <div className="flex flex-wrap gap-2">
            {topSymbols.map((row) => (
              <button
                key={row.symbol}
                type="button"
                onClick={() => setSelected(row.symbol)}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-left text-xs hover:bg-muted",
                  selected === row.symbol && "border-primary/60 bg-primary/5",
                )}
              >
                <span className="font-mono font-medium">{row.symbol}</span>
                <span className="ms-2 text-muted-foreground">{row.trades} {t("journal.trades")}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {selected && <SymbolChart symbol={selected} onClose={() => setSelected(null)} />}

      {hasRecords && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">{t("journal.ledger")}</h2>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-xs">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-start font-medium">{t("journal.colTime")}</th>
                  <th className="px-3 py-2 text-start font-medium">{t("journal.colSymbol")}</th>
                  <th className="px-3 py-2 text-start font-medium">{t("journal.colSide")}</th>
                  <th className="px-3 py-2 text-end font-medium">{t("journal.colQty")}</th>
                  <th className="px-3 py-2 text-end font-medium">{t("journal.colPrice")}</th>
                  <th className="px-3 py-2 text-end font-medium">{t("journal.colAmount")}</th>
                  <th className="px-3 py-2 text-end font-medium">{t("journal.colFee")}</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((row) => (
                  <tr key={row.trade_id} className="border-t">
                    <td className="px-3 py-1.5 tabular-nums text-muted-foreground">{row.datetime.slice(0, 16)}</td>
                    <td className="px-3 py-1.5">
                      <button type="button" className="font-mono hover:underline" onClick={() => setSelected(row.symbol)}>
                        {row.symbol}
                      </button>
                      {row.name ? <span className="ms-1.5 text-muted-foreground">{row.name}</span> : null}
                    </td>
                    <td className={cn("px-3 py-1.5", row.side === "buy" ? "text-danger" : row.side === "sell" ? "text-success" : "text-muted-foreground")}>
                      {t(`journal.side_${row.side}`)}
                    </td>
                    <td className="px-3 py-1.5 text-end tabular-nums">{row.quantity.toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-end tabular-nums">{fmtNumber(row.price)}</td>
                    <td className="px-3 py-1.5 text-end tabular-nums">{fmtNumber(row.amount)}</td>
                    <td className="px-3 py-1.5 text-end tabular-nums">{fmtNumber(row.fee)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {hasRecords && summary && summary.batches.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">{t("journal.imports")}</h2>
          <ul className="space-y-1.5">
            {summary.batches.map((batch) => (
              <li key={batch.import_id} className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs">
                <span className="font-medium">{batch.filename}</span>
                <span className="text-muted-foreground">{batch.format}</span>
                <span className="text-muted-foreground">
                  {batch.inserted} {t("journal.trades")}
                  {batch.duplicates > 0 ? ` · ${batch.duplicates} ${t("journal.duplicates")}` : ""}
                </span>
                <span className="ms-auto tabular-nums text-muted-foreground">{batch.created_at.slice(0, 16).replace("T", " ")}</span>
                <button
                  type="button"
                  aria-label={t("journal.delete")}
                  title={t("journal.delete")}
                  onClick={() => void onDeleteImport(batch.import_id)}
                  className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-danger"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: string; tone?: number }) {
  return (
    <div className="rounded-xl border bg-card p-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-lg font-semibold tabular-nums", tone !== undefined && tone > 0 && "text-success", tone !== undefined && tone < 0 && "text-danger")}>
        {value}
      </p>
    </div>
  );
}

function BehaviorCard({ title, metric }: { title: string; metric: JournalBehaviorMetric }) {
  const { t } = useTranslation();
  const tone =
    metric.severity === "high" ? "border-danger/40 bg-danger/5" : metric.severity === "medium" ? "border-warning/40 bg-warning/5" : "border-border";
  const badge =
    metric.severity === "high" ? "bg-danger/15 text-danger" : metric.severity === "medium" ? "bg-warning/15 text-warning" : "bg-muted text-muted-foreground";
  return (
    <div className={cn("rounded-xl border p-3", tone)}>
      <div className="flex items-center gap-2">
        <p className="text-sm font-medium">{title}</p>
        <span className={cn("rounded-full px-2 py-0.5 text-[10px]", badge)}>
          {t(`journal.severity_${metric.severity}`)}
        </span>
      </div>
      {metric.evidence && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{metric.evidence}</p>}
    </div>
  );
}

function MonthlyBars({ months }: { months: Array<{ month: string; pnl: number; trades: number }> }) {
  const max = Math.max(...months.map((month) => Math.abs(month.pnl)), 1);
  return (
    <div className="flex h-44 items-end gap-1 overflow-x-auto">
      {months.map((month) => {
        const height = Math.max(3, Math.round((Math.abs(month.pnl) / max) * 100));
        return (
          <div key={month.month} className="flex min-w-[28px] flex-1 flex-col items-center justify-end gap-1" title={`${month.month}: ${month.pnl}`}>
            <span className={cn("text-[9px] tabular-nums", month.pnl >= 0 ? "text-success" : "text-danger")}>
              {Math.round(month.pnl)}
            </span>
            <div
              className={cn("w-full rounded-sm", month.pnl >= 0 ? "bg-success/70" : "bg-danger/70")}
              style={{ height: `${height}%` }}
            />
            <span className="text-[9px] text-muted-foreground">{month.month.slice(2)}</span>
          </div>
        );
      })}
    </div>
  );
}

function SymbolChart({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [payload, setPayload] = useState<MarketOhlcResponse | null>(null);
  const [markers, setMarkers] = useState<TradeMarker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    (async () => {
      const own = await api.getJournalTrades(symbol, 2000);
      const dates = own.trades.map((row) => row.datetime.slice(0, 10)).sort();
      const start = dates[0] ? shiftDays(dates[0], -90) : undefined;
      const end = dates[dates.length - 1] ? shiftDays(dates[dates.length - 1], 5) : undefined;
      const next = await api.getMarketOhlc(symbol, { start, end, interval: "1D" }, controller.signal);
      if (controller.signal.aborted) return;
      setPayload(next);
      setMarkers(
        own.trades
          .filter((row) => row.side === "buy" || row.side === "sell")
          .map((row) => ({
            time: row.datetime.slice(0, 10),
            side: row.side === "buy" ? "BUY" : "SELL",
            price: row.price,
            qty: row.quantity,
          })),
      );
    })()
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : t("journal.chartFailed"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [symbol, t]);

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">
          {t("journal.chartTitle", { symbol })}
        </h2>
        <span className="text-[11px] text-muted-foreground">{t("journal.chartHint")}</span>
        <button type="button" onClick={onClose} className="ms-auto rounded border px-2 py-1 text-xs hover:bg-muted">
          {t("journal.hideChart")}
        </button>
      </div>
      <div className="rounded-xl border bg-card p-2">
        {loading ? (
          <div className="flex h-[420px] items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" /></div>
        ) : error ? (
          <div className="flex h-[420px] items-center justify-center text-sm text-danger">{error}</div>
        ) : payload && payload.bars.length > 0 ? (
          <CandlestickChart data={payload.bars} markers={markers} height={420} />
        ) : (
          <div className="flex h-[420px] items-center justify-center text-sm text-muted-foreground">{t("journal.chartEmpty")}</div>
        )}
      </div>
    </section>
  );
}
