// Drive a visitor's path in a real browser - no token - : a self-approval refused, a
// second person's decision recorded, a parsed docket confirmed, a bid
// resubmitted as a new revision, a soft delete undone. The token is used only
// for the reset at the end, which visitors cannot do.
//
//   BASE=http://localhost:5261 TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs

import { chromium } from "playwright";

const BASE = process.env.BASE || "http://localhost:5261";
const TOKEN = process.env.TOKEN || "";
const CHANNEL = process.env.BROWSER_CHANNEL || undefined;
const OUT = process.env.OUT || "./page-shots";
const browser = await chromium.launch(CHANNEL ? { channel: CHANNEL } : {});
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage();
page.on("dialog", (d) => d.accept());
let steps = 0;
const expect = async (name, locator) => {
  await locator.first().waitFor({ timeout: 25_000 });
  steps += 1;
  console.log(`ok   ${name}`);
};
const waitCount = async (locator, n, what) => {
  for (let i = 0; i < 50; i += 1) {
    if (await locator.count() === n) return;
    await page.waitForTimeout(200);
  }
  throw new Error(what);
};
const actAs = async (who, url) => {
  await page.evaluate((w) => sessionStorage.setItem("plexxcon_demo_actor", w), who);
  await page.goto(url, { waitUntil: "networkidle" });
};

await page.goto(`${BASE}/trade-planner`, { waitUntil: "networkidle" });
await expect("a visitor gets the open demo, no token", page.getByText("Open demo: changes reset when idle"));

await actAs("Site supervisor B", `${BASE}/trade-planner?tab=tracking&request=TR-0003`);
await page.getByLabel("Feedback").fill("Looks right to me");
await page.getByRole("button", { name: /Record the decision/ }).click();
await expect("the author cannot decide their own request", page.getByText("You cannot decide your own request"));

await actAs("Construction manager", `${BASE}/trade-planner?tab=tracking&request=TR-0003`);
await page.getByLabel("Feedback").fill("Crew sizes agree with the programme.");
await page.getByRole("button", { name: /Record the decision/ }).click();
await expect("a second person accepts it", page.getByText("TR-0003 accepted."));

await actAs("Contracts administrator A", `${BASE}/material-supply?job=2427&register=concrete`);
await page.getByRole("button", { name: "Review" }).first().click();
await expect("the parser reads the docket", page.getByText(/Parser: ridgeline_v1/));
await page.getByRole("button", { name: "Confirm and record" }).click();
await expect("a person confirms it and it is recorded", page.getByText(/Confirmed: docket recorded/));

await page.goto(`${BASE}/material-supply?job=2418&register=concrete&tab=invoices`, { waitUntil: "networkidle" });
const rows = page.getByRole("button", { name: /^Delete INV-/ });
const before = await rows.count();
await rows.first().click();
await expect("an invoice is soft-deleted", page.getByText(/deleted\. It is kept/));
await waitCount(rows, before - 1, "the deleted invoice is still listed");
await page.getByRole("button", { name: "Undo" }).click();
await waitCount(rows, before, "undo did not bring the invoice back");
steps += 1;
console.log("ok   and Undo brings it back");

await actAs("Estimator A", `${BASE}/bid-summary`);
await page.getByText("Yatala distribution centre hardstand", { exact: true }).click();
await page.getByRole("button", { name: "New revision from this" }).click();
await expect("a new revision starts from the latest", page.getByText("Autosaved").or(page.getByText("Shared draft")));
await page.getByLabel("Margin %").fill("6.5");
await page.getByRole("button", { name: "Submit", exact: true }).click();
await expect("submitting locks it as a new numbered revision", page.getByText(/Submitted as B-2629 revision 2/));
await page.screenshot({ path: `${OUT}/flow-submitted.png`, fullPage: true });

await page.goto(`${BASE}/bid-summary?tab=audit`, { waitUntil: "networkidle" });
await expect("the submission is in the audit log", page.getByText("B-2629 revision 2").first());

await page.goto(`${BASE}/balance-sheet`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Drill up" }).click();
await waitCount(page.getByRole("button", { name: "Entries behind Cash at bank" }), 0, "drill up left the accounts showing");
await page.getByRole("button", { name: "Drill down" }).click();
await page.getByRole("button", { name: "Entries behind Cash at bank" }).click();
await expect("a balance drills to entries that agree with it", page.getByText("Agrees with the statement"));
await page.keyboard.press("Escape");
await page.goto(`${BASE}/profit-and-loss`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: /^Entries behind Contract revenue, / }).first().click();
await expect("a month's figure drills to that month's entries", page.getByText("Agrees with the statement"));

const reset = await page.evaluate(async (tok) => (await fetch("/api/reset", { method: "POST", headers: { "X-Write-Token": tok } })).status, TOKEN);
if (reset !== 200) throw new Error(`reset returned ${reset}`);
await browser.close();
console.log(`\n${steps} steps passed`);
