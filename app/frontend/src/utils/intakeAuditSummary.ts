export type IntakeAudit = {
  runId?: string;
  expected?: number;
  present?: number;
  missing?: number;
  unreadable?: number;
  ambiguous?: number;
  duplicateItemCount?: number;
  ready?: boolean;
  rows?: {
    sequence?: number;
    labelJa?: string;
    expectedFileName?: string;
    issues?: string[];
    actionNeeded?: string;
  }[];
};

export function summarizeIntakeAudit(audit: IntakeAudit): {
  headline: string;
  ok: boolean;
  bullets: string[];
} {
  const expected = audit.expected ?? 0;
  const present = audit.present ?? 0;
  const missing = audit.missing ?? 0;
  const unreadable = audit.unreadable ?? 0;
  const ambiguous = audit.ambiguous ?? 0;
  const duplicates = audit.duplicateItemCount ?? 0;

  const bullets: string[] = [];
  if (missing > 0) {
    const names =
      audit.rows
        ?.filter((r) => r.issues?.includes("missing"))
        .slice(0, 5)
        .map((r) => r.expectedFileName ?? `#${r.sequence}`)
        .join(", ") ?? "";
    bullets.push(`不足 ${missing} 件${names ? `: ${names}` : ""}`);
  }
  if (ambiguous > 0) {
    bullets.push(`ソースが曖昧 ${ambiguous} 件（同名候補が複数）`);
  }
  if (unreadable > 0) {
    bullets.push(`読み取り不可 ${unreadable} 件`);
  }
  if (duplicates > 0) {
    bullets.push(`重複候補 ${duplicates} 件`);
  }

  const ok = Boolean(audit.ready);
  const headline = ok
    ? `${present}/${expected} 件すべて取り込み可能です`
    : `${present}/${expected} 件検出 — 取り込み前に ${missing + ambiguous + unreadable} 件要確認`;

  return { headline, ok, bullets };
}
