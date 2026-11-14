import { CalendarClock, LineChart, NotebookPen, WalletCards } from "lucide-react";

// Local profile: only the trading cockpit is exposed (行情 / 交易复盘 / 账户持仓 /
// 定时任务). Everything else stays routed but is commented out of the sidebar so
// it can be restored by uncommenting the entries below.
//
// Disabled modules (routes kept alive in router.tsx):
//   agent, reports, researchArtifacts, paperTrading, alphaZoo, researchLab,
//   optionsLab, correlation, pixelOffice, runtime, settings
export const NAVIGATION_GROUPS = [
  { id: "trading", items: [
    { id: "market", to: "/market", icon: LineChart },
    { id: "journal", to: "/journal", icon: NotebookPen },
    { id: "portfolio", to: "/portfolio", icon: WalletCards },
    { id: "scheduled", to: "/scheduled", icon: CalendarClock },
  ] },
  // { id: "research", items: [
  //   { id: "agent", to: "/", icon: Bot },
  //   { id: "reports", to: "/reports", icon: FileText },
  //   { id: "researchArtifacts", to: "/research-artifacts", icon: BookOpen },
  //   { id: "paperTrading", to: "/paper-trading", icon: FlaskConical },
  //   { id: "portfolio", to: "/portfolio", icon: WalletCards },
  //   { id: "journal", to: "/journal", icon: NotebookPen },
  // ] },
  // { id: "analysis", items: [
  //   { id: "market", to: "/market", icon: LineChart },
  //   { id: "alphaZoo", to: "/alpha-zoo", icon: Layers },
  //   { id: "researchLab", to: "/research-lab", icon: FlaskConical },
  //   { id: "optionsLab", to: "/options", icon: CandlestickChart },
  //   { id: "correlation", to: "/correlation", icon: BarChart3 },
  // ] },
  // { id: "automation", items: [
  //   { id: "pixelOffice", to: "/pixel-office", icon: Building2 },
  //   { id: "scheduled", to: "/scheduled", icon: CalendarClock },
  //   { id: "runtime", to: "/runtime", icon: Activity },
  //   { id: "settings", to: "/settings", icon: Settings },
  // ] },
] as const;

export type NavigationItem = typeof NAVIGATION_GROUPS[number]["items"][number];

export function isNavigationActive(to: string, pathname: string): boolean {
  return to === "/" ? pathname === "/" || pathname === "/agent"
    : pathname === to || pathname.startsWith(`${to}/`);
}
