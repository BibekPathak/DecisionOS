/**
 * Typed client for the DecisionOS API.
 *
 * All pages fetch through these helpers so the API base URL and error handling
 * live in one place. The dashboard is read-mostly; it never fabricates data.
 */

export const API_BASE_URL =
  process.env.DECISIONOS_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export interface DecisionEvent {
  type: string;
  from_state: string | null;
  to_state: string | null;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface PolicySummary {
  name: string;
  version: number;
  precedence: string;
  overridden: boolean;
  triggered_rules: string[];
}

export interface Decision {
  decision_id: string;
  decision_type: string;
  schema_name: string;
  schema_version: number;
  action: string;
  model_action: string;
  confidence: number;
  probabilities: Record<string, number>;
  risk: number | null;
  reason_codes: string[];
  provider: string;
  provider_request_id: string | null;
  latency_ms: number;
  state: string | null;
  policy: PolicySummary | null;
  created_at: string;
}

export interface Explanation {
  decision_id: string;
  decision: string;
  model_action: string;
  model_probabilities: Record<string, number>;
  confidence: number;
  risk: number | null;
  reason_codes: string[];
  policy_rules_triggered: string[];
  policy_precedence: string | null;
  provider: string;
  schema_name: string;
  schema_version: number;
  lifecycle: DecisionEvent[];
}

export interface Outcome {
  decision_id: string;
  actual_outcome: string;
  success: boolean;
  metadata: Record<string, unknown>;
  recorded_at: string;
}

export interface Schema {
  name: string;
  version: number;
  actions: string[];
  description: string | null;
  action_descriptions: Record<string, string | null>;
  created_at: string;
}

export interface PolicyRule {
  name: string;
  when: Record<string, unknown>;
  require: string;
}

export interface Policy {
  name: string;
  version: number;
  description: string | null;
  rules: PolicyRule[];
}

export interface CalibrationBucket {
  lower: number;
  upper: number;
  count: number;
  accuracy: number;
  avg_confidence: number;
}

export interface CalibrationReport {
  sample_count: number;
  brier_score: number | null;
  expected_calibration_error: number | null;
  buckets: CalibrationBucket[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    let detail = `request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the default message
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export interface DecisionListParams {
  decision_type?: string;
  schema_name?: string;
  provider?: string;
  action?: string;
  limit?: number;
  offset?: number;
}

export async function listDecisions(
  params: DecisionListParams = {}
): Promise<Decision[]> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Decision[]>(`/v1/decisions${suffix}`);
}

export async function getDecision(decisionId: string): Promise<Decision> {
  return apiFetch<Decision>(`/v1/decisions/${decisionId}`);
}

export async function getExplanation(
  decisionId: string
): Promise<Explanation> {
  return apiFetch<Explanation>(`/v1/decisions/${decisionId}/explanation`);
}

export async function listSchemas(): Promise<Schema[]> {
  return apiFetch<Schema[]>("/v1/schemas");
}

export async function listPolicies(): Promise<Policy[]> {
  return apiFetch<Policy[]>("/v1/policies");
}

export interface CalibrationParams {
  decision_type?: string;
  provider?: string;
  action?: string;
}

export async function getCalibration(
  params: CalibrationParams = {}
): Promise<CalibrationReport> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<CalibrationReport>(`/v1/calibration${suffix}`);
}
