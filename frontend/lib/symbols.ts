const EXCHANGE_SUFFIX = /\.(?:SS|SZ|SH|BJ)$/i;

/**
 * Normalize a user- or list-supplied A-share symbol to the bare six-digit code
 * that /market/history and <CompanyKline> expect.
 *
 * Accepts "600519.SS", "600519.SH", "000001.SZ", "sh600519", "600519", ...
 * and simply keeps the digits, so leading zeros are preserved.
 */
export function toSixDigit(symbol: string): string {
  return String(symbol ?? "")
    .trim()
    .toUpperCase()
    .replace(EXCHANGE_SUFFIX, "")
    .replace(/\D/g, "");
}
