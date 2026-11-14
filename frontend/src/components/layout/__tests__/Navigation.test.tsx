import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "@/i18n";
import { SidebarNavigation } from "../SidebarNavigation";
import { PageHelp } from "../PageHelp";

beforeAll(async () => { await i18n.changeLanguage("en"); });

function renderNavigation(path = "/", collapsed = false) {
  return render(<MemoryRouter initialEntries={[path]}><SidebarNavigation collapsed={collapsed} /><PageHelp /></MemoryRouter>);
}

it("exposes only the four trading modules", () => {
  renderNavigation("/market");
  const region = screen.getByRole("region", { name: "Trading" });
  expect(within(region).getAllByRole("link").map((link) => link.getAttribute("href")))
    .toEqual(["/market", "/journal", "/portfolio", "/scheduled"]);
  expect(screen.getByRole("link", { name: "Market" })).toHaveAttribute("aria-current", "page");
});

it("keeps page help for the journal module", () => {
  renderNavigation("/journal");
  fireEvent.click(screen.getByText("How to use Trade journal"));
  expect(screen.getByText(/Import a broker statement/)).toBeVisible();
});

it("opens the compact menu and returns focus on Escape", () => {
  renderNavigation("/market", true);
  const trigger = screen.getByRole("button", { name: "Browse features" });
  fireEvent.click(trigger);
  const menu = screen.getByRole("navigation", { name: "Browse features" });
  expect(within(menu).getByText("Trade journal")).toBeVisible();
  expect(within(menu).getAllByRole("link")).toHaveLength(4);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("navigation", { name: "Browse features" })).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("navigates from the compact menu", () => {
  renderNavigation("/market", true);
  fireEvent.click(screen.getByRole("button", { name: "Browse features" }));
  const menu = screen.getByRole("navigation", { name: "Browse features" });
  fireEvent.click(within(menu).getByRole("link", { name: "Account holdings" }));
  expect(screen.queryByRole("navigation", { name: "Browse features" })).not.toBeInTheDocument();
});
