export type FilterQuery = {
  month: string;
  start: string;
  end: string;
  accounts: string[];
  statuses: string[];
  search: string;
};

export function buildFilterHref(pathname: string, filters: FilterQuery, accounts: string[], statuses: string[]) {
  const query = new URLSearchParams();
  query.set("month", filters.month);
  query.set("start", filters.start);
  query.set("end", filters.end);
  if (filters.accounts.length !== accounts.length) filters.accounts.forEach((account) => query.append("account", account));
  if (statuses.length && filters.statuses.length !== statuses.length) filters.statuses.forEach((status) => query.append("status", status));
  if (filters.search.trim()) query.set("search", filters.search.trim());
  return `${pathname}?${query.toString()}`;
}
