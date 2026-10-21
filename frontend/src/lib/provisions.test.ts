import { describe, expect, it } from "vitest";

import type { Planned, Recurring } from "../api/budget";
import { provisions, totalPerMonth } from "./provisions";

const planned = (date: string, amount: string, extra: Partial<Planned> = {}): Planned => ({
  id: date,
  date,
  description: "IPVA",
  amount,
  category_id: null,
  notes: null,
  expense_id: null,
  ...extra,
});

const yearly = (start: string, amount: string, interval: 1 | 2 | 3 | 6 | 12 = 12): Recurring => ({
  id: start,
  kind: "expense",
  description: "IPTU",
  amount,
  category_id: null,
  due_day: 10,
  start_month: `${start}-01`,
  end_month: null,
  interval_months: interval,
  income_type: null,
  payment_method: null,
  notes: null,
});

describe("provisões para gastos sazonais", () => {
  it("despesa prevista: divide pelos meses até lá", () => {
    const [p] = provisions([planned("2027-03-15", "1500.00")], [], "2026-10-21");
    expect(p).toMatchObject({ months: 5, perMonth: 300 });
  });

  it("conta anual: a próxima vez depois deste mês", () => {
    const [p] = provisions([], [yearly("2026-02", "1200.00")], "2026-10-21");
    expect(p).toMatchObject({ date: "2027-02-10", months: 4, perMonth: 300 });
  });

  it("fica de fora: já lançada, deste mês, mensal, longe demais", () => {
    const list = provisions(
      [planned("2026-10-30", "100.00"), planned("2027-02-01", "100.00", { expense_id: "x" }), planned("2028-05-01", "100.00")],
      [yearly("2026-01", "50.00", 1)],
      "2026-10-21",
    );
    expect(list).toEqual([]);
  });

  it("soma por mês", () => {
    const list = provisions([planned("2027-03-15", "1500.00")], [yearly("2026-02", "1200.00")], "2026-10-21");
    expect(totalPerMonth(list)).toBe(600);
    expect(list.map((p) => p.description)).toEqual(["IPTU", "IPVA"]);
  });
});
