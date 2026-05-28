import type {
  AppSettings,
} from "../types";

export const mockSettings: AppSettings = {
  // Default destination folders — new profiles pre-fill from these.
  processedFolder: "C:\\FileGuardian\\processed\\good",
  quarantineFolder: "C:\\FileGuardian\\processed\\quarantine",
  reviewFolder: "C:\\FileGuardian\\processed\\review",
  pollIntervalSeconds: 5,
  notificationChannel: "email",
  smtpHost: "smtp.xorbix.com",
  smtpPort: 587,
  smtpFrom: "fileguardian@xorbix.com",
  teamsWebhookUrl: "",
  defaultRecipients: ["ops-team@xorbix.com"],
};
