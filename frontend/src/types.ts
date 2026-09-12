export type Value = string | number;
export interface Issue { name: string; values?: Value[]; total?: number }
export interface Domain { schema_version: number; name: string; issues: Issue[] }
export interface Profile {
  weights: Record<string, number>;
  scores: Record<string, { value: Value; score: number }[]>;
  provenance: string; reservation: number; conversion: string | null;
}
export interface Condition { score_targets?: Record<string, number>; reward_minimums?: Record<string, number>; gestures?: boolean; block?: string | null; break_after_seconds?: number; output_device?: string | null; output?: string | null; domain?: string | Domain | null; label: string; strategy: string; duration_seconds: number; practice: boolean }
export interface SurveyItem { id: string; prompt: string; minimum: number; maximum: number;
  phase: string; required?: boolean; source?: string; include_practice?: boolean }
export interface StudySpec {
  interaction_protocol?: 'direct-offer' | 'ready-offer-response';
  purpose?: 'demonstration' | 'published-protocol' | 'custom-study'; protocol?: Record<string, unknown>;
  study_id: string; participant_id: string; title: string; instructions: string;
  domain: string | Domain; preference_mode: 'elicited' | 'assigned';
  human_profile?: Profile; agent_profile?: Profile;
  conditions: Condition[]; order: string; participant_index: number;
  manual_affect?: boolean; speech_device?: string | null; perception_device?: string | null;
  cohort: string; seed: number; first_actor: string; output: string; surveys: SurveyItem[];
}
export interface OfferRecord { offer_id: string; actor: 'human' | 'agent'; bid: Record<string, Value>;
  utilities: { human: number; agent?: number }; round: number; elapsed_seconds: number; sequence: number }
export interface Outcome { payoffs?: {human:number;agent?:number} | null; reason: string; agreement: Record<string, Value> | null;
  utilities: { human: number; agent?: number } | null }
export interface Session {
  config: { score_targets?: Record<string, number>; reward_minimums?: Record<string, number>; session_id: string; duration_seconds: number; practice: boolean; sequence_index: number; strategy?: string };
  interaction_phase: string; status: string; next_actor: string; offers: OfferRecord[]; outcome: Outcome | null;
  terminal_event_id: string | null; remaining_seconds: number; elapsed_fraction: number; sequence: number;
}
export interface Study {
  purpose?: string; readiness?: { id: string; reason: string }[]; break_remaining_seconds: number; break_restarted: boolean;
  plan_id: string; title: string; instructions: string; participant_id: string;
  manual_affect: boolean; speech_available: boolean; perception_available: boolean; presentation_pending: boolean;
  phase: string; phase_id: string; sequence_index: number; session_count: number; domain: Domain; human_profile: Profile;
  current: Session | null; survey_phase: string | null; survey_items: SurveyItem[]; output: string;
  completed_sessions: { session_id: string; sequence_index: number; practice: boolean; outcome: Outcome }[];
  error: string | null; participant_token?: string; spec?: StudySpec; conditions?: Condition[];
  agent_profile?: Profile; config_version?: number;
}
export interface Catalog { strategies: string[]; domains: Record<string, Domain>; outputs: string[]; devices: Record<string, { family: string; capabilities: string[] }> }
export interface Draft { transcript: string; missing: string[]; ambiguous: string[]; invalid: string[]; intent: string }
export interface CommandResult { committed: boolean; draft: Draft | null; state: Study }
export const issueValues = (issue: Issue): Value[] => issue.values ?? Array.from({ length: (issue.total ?? 0) + 1 }, (_, i) => i);
export const score = (value: number | undefined | null) => value == null ? '—' : (100 * value).toFixed(1);
export const newRequest = () => crypto.randomUUID();
