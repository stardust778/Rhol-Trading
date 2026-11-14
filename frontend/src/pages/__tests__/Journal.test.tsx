import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Journal } from "@/pages/Journal";
import { api } from "@/lib/api";
import i18n from "@/i18n";

vi.mock("@/components/charts/CandlestickChart", () => ({ CandlestickChart: () => null }));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getJournalSummary: vi.fn(),
      getJournalAnalysis: vi.fn(),
      getJournalTrades: vi.fn(),
      uploadFile: vi.fn(),
      importJournal: vi.fn(),
      deleteJournalImport: vi.fn(),
    },
  };
});

const mocked = api as unknown as {
  getJournalSummary: ReturnType<typeof vi.fn>;
  getJournalAnalysis: ReturnType<typeof vi.fn>;
  getJournalTrades: ReturnType<typeof vi.fn>;
};

const EMPTY_SUMMARY = {
  records: 0, symbols: 0, first_date: null, last_date: null, imports: 0, batches: [],
};

const TRADE = {
  trade_id: "t1",
  datetime: "2026-10-09 09:35:12",
  symbol: "000001.SZ",
  name: "平安银行",
  side: "buy" as const,
  quantity: 1000,
  price: 11.8,
  amount: 11800,
  fee: 5.1,
  market: "china_a",
};

beforeAll(async () => {
  await i18n.changeLanguage("en");
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Journal page", () => {
  it("shows the import call to action when no fills are stored", async () => {
    mocked.getJournalSummary.mockResolvedValue(EMPTY_SUMMARY);
    mocked.getJournalAnalysis.mockResolvedValue({ status: "empty", records: 0 });
    mocked.getJournalTrades.mockResolvedValue({ status: "ok", symbol: null, count: 0, trades: [] });

    render(<Journal />);

    expect(await screen.findByText("No trades imported yet")).toBeInTheDocument();
    expect(screen.getByText(/Export a 交割单 or 对账单/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Import statement/ })).toBeInTheDocument();
  });

  it("renders profile, behaviour diagnostics and the ledger", async () => {
    mocked.getJournalSummary.mockResolvedValue({
      records: 2,
      symbols: 1,
      first_date: "2026-10-09 09:35:12",
      last_date: "2026-10-15 14:20:01",
      imports: 1,
      batches: [
        {
          import_id: "abc123",
          filename: "招商交割单.csv",
          format: "cn_broker",
          records: 2,
          inserted: 2,
          duplicates: 0,
          first_date: "2026-10-09 09:35:12",
          last_date: "2026-10-15 14:20:01",
          created_at: "2026-11-14T06:12:50+00:00",
        },
      ],
    });
    mocked.getJournalAnalysis.mockResolvedValue({
      status: "ok",
      records: 2,
      date_range: "2026-10-09 ~ 2026-10-15",
      symbols: 1,
      profile: {
        total_trades: 2,
        total_roundtrips: 1,
        avg_holding_days: 6.2,
        trade_frequency_per_week: 2.3,
        win_rate: 1,
        profit_loss_ratio: null,
        total_pnl: 283.75,
        max_drawdown: 0,
        top_symbols: [{ symbol: "000001.SZ", trades: 2, total_amount: 23900 }],
      },
      behavior: {
        disposition_effect: { severity: "low", evidence: "Losing roundtrips held 2.0d vs winning 4.0d." },
        overtrading: { severity: "medium", evidence: "Busy days underperform quiet days." },
        chasing_momentum: { severity: "low", evidence: "not enough repeat buys" },
        anchoring: { severity: "low", evidence: "no symbol has ≥5 trades" },
      },
      monthly_pnl: [{ month: "2026-10", pnl: 283.75, trades: 1, wins: 1, losses: 0 }],
      roundtrips: [],
    });
    mocked.getJournalTrades.mockResolvedValue({
      status: "ok",
      symbol: null,
      count: 1,
      trades: [TRADE],
    });

    render(<Journal />);

    expect(await screen.findByText("Disposition effect")).toBeInTheDocument();
    expect(screen.getByText("Overtrading")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
    expect(screen.getByText("Losing roundtrips held 2.0d vs winning 4.0d.")).toBeInTheDocument();
    expect(screen.getByText("Realised P&L")).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByText("283.75")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "000001.SZ" })).toBeInTheDocument();
    expect(screen.getByText("招商交割单.csv")).toBeInTheDocument();
  });
});
