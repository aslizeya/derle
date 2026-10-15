"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { useDatasets } from "@/lib/api/hooks";

/** The dataset a workspace-level page works on: the user's pick, else the largest one. */
export function useActiveDataset(ws: number) {
  const datasets = useDatasets(ws);
  const [picked, setPicked] = useState<number | undefined>();
  const largest = [...(datasets.data ?? [])].sort((a, b) => b.records - a.records)[0];
  const active = datasets.data?.find((d) => d.id === picked) ?? largest;
  return { datasets, active, setPicked };
}

export function DatasetSelect({
  ws,
  value,
  onChange,
}: {
  ws: number;
  value: number | undefined;
  onChange: (id: number) => void;
}) {
  const t = useTranslations("dashboard");
  const datasets = useDatasets(ws);
  if (!datasets.data || datasets.data.length < 2) return null;
  return (
    <label className="inline-flex items-center gap-2 text-sm text-ink-muted">
      {t("dataset")}
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-9 rounded-lg border border-rule-strong bg-paper-raised px-2 text-sm text-ink"
      >
        {datasets.data.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>
    </label>
  );
}
