// Integer arithmetic, the same as backend/src/app/calc/money.py. No float
// decides a figure, so the browser's preview and the server's record agree
// to the cent.

export function rhu(numerator, denominator) {
  if (denominator <= 0) throw new Error("denominator must be positive");
  if (numerator < 0) return -rhu(-numerator, denominator);
  return Math.floor((2 * numerator + denominator) / (2 * denominator));
}

export function ceilDiv(n, d) {
  return -Math.floor(-n / d);
}

function parseScaled(value, digits) {
  if (value == null || value === "") return 0;
  let text = String(value).replace(/[,$]/g, "").trim();
  const negative = text.startsWith("-");
  text = text.replace(/^[+-]+/, "");
  const [whole = "", frac = ""] = text.split(".", 2);
  if ((!whole && !frac) || !/^\d*$/.test(whole) || !/^\d*$/.test(frac) || text.split(".").length > 2) {
    throw new Error(`not a number: ${value}`);
  }
  const padded = (frac + "0".repeat(digits + 1)).slice(0, digits + 1);
  const scaled = Number(whole || "0") * 10 ** digits + Number(padded.slice(0, digits) || "0") + (Number(padded[digits]) >= 5 ? 1 : 0);
  return negative ? -scaled : scaled;
}

export function toCents(value) {
  return parseScaled(value, 2);
}

export function toScaled(value, scale) {
  return parseScaled(value, String(scale).length - 1);
}

export function safe(fn, fallback = 0) {
  try { return fn(); } catch { return fallback; }
}
