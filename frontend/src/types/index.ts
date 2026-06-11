// =========================================================================
// Validation run types
// =========================================================================

export type RunStatus =
  | "passed"
  | "failed"
  | "processing"
  | "quarantined"
  | "review";

export type IssueSeverity = "error" | "warning" | "info";

export interface ValidationIssue {
  id: string;
  rule: string;
  severity: IssueSeverity;
  message: string;
  location?: string; // e.g. "row 14, column Amount"
  columnName?: string;
  rowNumber?: number;
  constraintKind?:
    | "type"
    | "min"
    | "max"
    | "regex"
    | "allowed_values"
    | "unique"
    | "required"
    | "cross"
    | "missing_column";
}

export interface AgentEvent {
  agent:
    | "Monitor"
    | "Intake"
    | "Planning"
    | "Test"
    | "Explanation"
    | "Notification"
    | "Audit";
  action: string;
  timestamp: string; // ISO
  detail?: string;
}

export interface AiSummary {
  summary: string;
  impact?: string;
  action?: string;
}

export interface ColumnStat {
  columnName: string;
  totalCount: number;
  blankCount: number;
  distinctCount: number;
  distinctTruncated: boolean;
  numericMin?: number | null;
  numericMax?: number | null;
  numericMean?: number | null;
  textMinLength?: number | null;
  textMaxLength?: number | null;
  topValues: { value: string; count: number }[];
}

export interface ValidationRun {
  id: string;
  fileName: string;
  receivedAt: string; // ISO
  completedAt?: string; // ISO
  status: RunStatus;
  profileId: string;
  profileName: string;
  issueCount: number;
  errorCount: number;
  warningCount: number;
  totalRows?: number | null;
  columnCount?: number | null;
  notificationStatus: "sent" | "not_required" | "failed" | "pending";
  notifiedRecipients?: string[];
  fileSizeKb: number;
  destinationPath?: string;
  aiSummary: AiSummary;
  issues: ValidationIssue[];
  events: AgentEvent[];
  columnStats?: ColumnStat[];
}

// =========================================================================
// Validation profile types — per-column constraint model
// =========================================================================

export type ColumnType =
  | "string"
  | "integer"
  | "decimal"
  | "date"
  | "datetime"
  | "email"
  | "boolean";

export type ConstraintSeverity = "error" | "warning";

export type CrossColumnOp = "gt" | "gte" | "lt" | "lte" | "eq" | "neq";

/**
 * The set of constraints applied to a single column. Any field may be absent.
 * An empty object (apart from severity) means: "we just expect this column
 * header to be present — no content checks".
 */
export interface ColumnConstraints {
  required?: boolean;
  unique?: boolean;
  type?: ColumnType;
  /** Numbers, or ISO 8601 strings for date/datetime columns. */
  min?: number | string;
  max?: number | string;
  regex?: string;
  allowedValues?: string[];
  severity: ConstraintSeverity;
}

export interface ProfileColumn {
  id: string;
  name: string;
  order: number;
  description?: string;
  constraints: ColumnConstraints;
}

export interface CrossColumnRule {
  id: string;
  name: string;
  leftColumn: string;
  op: CrossColumnOp;
  rightColumn: string;
  severity: ConstraintSeverity;
}

export interface ValidationProfile {
  id: string;
  name: string;
  description: string;
  active: boolean;

  filePattern: string;
  fileType: "CSV" | "JSON" | "XML";

  columns: ProfileColumn[];
  crossColumnRules: CrossColumnRule[];

  /** If false, the presence of any non-declared column is itself an error. */
  allowExtraColumns: boolean;

  /** Folder this profile watches for incoming files. Required, per-profile. */
  inboundFolder: string;
  failureRouting: string;
  successRouting: string;
  unknownRouting: string;

  notifyOnFailure: boolean;
  recipients: string[];

  createdAt: string;
  updatedAt: string;
}

// =========================================================================
// App settings
// =========================================================================

export interface AppSettings {
  // NOTE: inbound folders are configured per-profile (see ValidationProfile.inboundFolder).
  // The fields below act as default destinations new profiles pre-fill with.
  processedFolder: string;
  quarantineFolder: string;
  reviewFolder: string;
  pollIntervalSeconds: number;
  notificationChannel: "email" | "teams" | "both";
  smtpHost: string;
  smtpPort: number;
  smtpFrom: string;
  teamsWebhookUrl: string;
  defaultRecipients: string[];

  // AI provider settings (the API keys themselves live in the .env, not here).
  aiProvider: "off" | "anthropic" | "openai" | "local" | "vertex" | "claudecli";
  aiModel: string;
  aiBaseUrl: string;
  vertexProject: string;
  vertexLocation: string;
  aiCliPath: string;
}
