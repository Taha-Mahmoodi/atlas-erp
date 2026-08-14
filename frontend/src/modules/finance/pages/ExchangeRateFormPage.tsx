/**
 * Create an exchange rate (STRUCTURE §4, PLAN 15.12, D-019). The rate is a decimal string
 * kept at full precision (D-015 — never floated); SPOT rates drive posting-time
 * translation, CLOSING rates period-end revaluation.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateExchangeRate, useCurrencyOptions } from "@/modules/finance/hooks";
import type { RateType } from "@/modules/finance/types";

export function ExchangeRateFormPage() {
  const navigate = useNavigate();
  const currencies = useCurrencyOptions();
  const createRate = useCreateExchangeRate();

  const [values, setValues] = useState<FormValues>({ rate_type: "SPOT" });
  const [error, setError] = useState<string | null>(null);

  const currencyOptions = (currencies.data?.items ?? []).map((currency) => ({
    value: currency.code,
    label: `${currency.code} — ${currency.name}`,
  }));

  const fields: FieldDef[] = [
    { name: "rate_date", label: "Rate date", type: "date", required: true, span: 1 },
    {
      name: "rate_type",
      label: "Rate type",
      type: "select",
      required: true,
      span: 1,
      options: [
        { value: "SPOT", label: "Spot (posting-time translation)" },
        { value: "CLOSING", label: "Closing (period-end revaluation)" },
      ],
    },
    { name: "from_currency_code", label: "From currency", type: "select", required: true, options: currencyOptions, span: 1 },
    { name: "to_currency_code", label: "To currency", type: "select", required: true, options: currencyOptions, span: 1 },
    { name: "rate", label: "Rate", type: "number", required: true, step: "0.000001", span: 1, help: "How many units of the to-currency one from-currency unit buys." },
  ];

  const submit = async () => {
    setError(null);
    if (values.from_currency_code === values.to_currency_code) {
      setError("From and to currencies must differ.");
      return;
    }
    try {
      await createRate.mutateAsync({
        rate_date: String(values.rate_date ?? ""),
        from_currency_code: String(values.from_currency_code ?? ""),
        to_currency_code: String(values.to_currency_code ?? ""),
        rate_type: String(values.rate_type ?? "SPOT") as RateType,
        rate: String(values.rate ?? ""),
      });
      void navigate({ to: "/finance/exchange-rates" });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the exchange rate."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance/exchange-rates">Exchange Rates</Link> /{" "}
          <span className="text-ink">New exchange rate</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">New exchange rate</h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fields}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel="Create rate"
          busy={createRate.isPending}
        />
      </div>
    </div>
  );
}
