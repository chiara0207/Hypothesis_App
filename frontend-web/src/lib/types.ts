export type AssumptionCheck = {
  name: string;
  passed: boolean;
  detail: string;
};

export type StatTestResult = {
  test_name: string;
  test_display_name: string;
  variables_used: Record<string, string>;
  rationale: string;
  statistic?: number | null;
  p_value?: number | null;
  additional_stats: Record<string, unknown>;
  assumption_checks: AssumptionCheck[];
  interpretation: string;
  plain_explanation: string;
  significant?: boolean | null;
  alpha: number;
  error?: string | null;
};

export type StatsHistoryEntry = {
  question: string;
  result: StatTestResult;
  sessionId: string;
};
