/**
 * Match tolerance settings (STRUCTURE §4): a single tenant-wide config, not a list of
 * resources — GET returns null until first configured (default 0/0, meaning strict: any price
 * or quantity deviation on a line is an exception until a tolerance is set here).
 */

import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useMatchTolerance, useSetMatchTolerance } from "@/modules/procurement/hooks";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

export function MatchToleranceFormPage() {
  const tolerance = useMatchTolerance();
  const setTolerance = useSetMatchTolerance();

  const [priceTolerance, setPriceTolerance] = useState("0");
  const [quantityTolerance, setQuantityTolerance] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (tolerance.data) {
      setPriceTolerance(tolerance.data.price_tolerance_percent);
      setQuantityTolerance(tolerance.data.quantity_tolerance_percent);
    }
  }, [tolerance.data]);

  const submit = async () => {
    setError(null);
    setSaved(false);
    try {
      await setTolerance.mutateAsync({
        price_tolerance_percent: priceTolerance,
        quantity_tolerance_percent: quantityTolerance,
      });
      setSaved(true);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the match tolerance."));
    }
  };

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-xl font-semibold text-ink">Match Tolerance</h1>
      <p className="mt-1 text-sm text-ink-muted">
        A 3-way match line is within tolerance only if both its price and quantity variance stay
        at or below these percentages. Without a saved tolerance, any deviation is an exception.
      </p>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {saved && (
        <p className="mt-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">Saved.</p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="price-tolerance" className="mb-1 block text-xs font-medium text-ink-muted">
            Price tolerance (%)
          </label>
          <input
            id="price-tolerance"
            type="number"
            step="0.01"
            value={priceTolerance}
            onChange={(event) => setPriceTolerance(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="quantity-tolerance" className="mb-1 block text-xs font-medium text-ink-muted">
            Quantity tolerance (%)
          </label>
          <input
            id="quantity-tolerance"
            type="number"
            step="0.01"
            value={quantityTolerance}
            onChange={(event) => setQuantityTolerance(event.target.value)}
            className={CONTROL}
          />
        </div>
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={setTolerance.isPending}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {setTolerance.isPending ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
