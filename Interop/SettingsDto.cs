using System;
using System.Text.Json.Serialization;

namespace UTPCalendar.Interop
{
    public class SettingsDto
    {
        [JsonPropertyName("use_custom_date_range")]
        public bool UseCustomDateRange { get; set; } = false;

        [JsonPropertyName("search_range_months")]
        public int SearchRangeMonths { get; set; } = 2;

        [JsonPropertyName("custom_start_date")]
        public DateTimeOffset? CustomStartDate { get; set; }

        [JsonPropertyName("custom_end_date")]
        public DateTimeOffset? CustomEndDate { get; set; }

        [JsonPropertyName("last_holidays_update")]
        public string LastHolidaysUpdate { get; set; } = "Nunca";

        // CORRECCIÓN CLAVE: URLs seguras por defecto para instalaciones nuevas
        [JsonPropertyName("login_url")]
        public string LoginUrl { get; set; } = "https://sso.utp.edu.pe/auth/realms/Xpedition/protocol/openid-connect/auth?client_id=utpmas-web&redirect_uri=https%3A%2F%2Fportal.utp.edu.pe%2F&response_mode=fragment&response_type=code&scope=openid";

        [JsonPropertyName("schedule_url")]
        public string ScheduleUrl { get; set; } = "https://portal.utp.edu.pe/calendario";

        [JsonPropertyName("date_input_mode")]
        public string DateInputMode { get; set; } = "dropdown";

        [JsonPropertyName("default_username")]
        public string DefaultUsername { get; set; } = string.Empty;

        [JsonPropertyName("last_ics_generated")]
        public string LastIcsGenerated { get; set; } = "Nunca";

        [JsonPropertyName("last_nextcloud_upload")]
        public string LastNextcloudUpload { get; set; } = "Nunca";

        [JsonPropertyName("subscription_ics_url")]
        public string SubscriptionIcsUrl { get; set; } = string.Empty;

        [JsonPropertyName("reminders_enabled")]
        public bool RemindersEnabled { get; set; }

        [JsonPropertyName("nextcloud_upload_enabled")]
        public bool NextcloudUploadEnabled { get; set; }

        [JsonPropertyName("autostart_enabled")]
        public bool AutostartEnabled { get; set; }

        [JsonPropertyName("first_event_reminder_minutes")]
        public int FirstEventReminderMinutes { get; set; } = 120;

        [JsonPropertyName("other_events_reminder_minutes")]
        public int OtherEventsReminderMinutes { get; set; } = 5;

        [JsonPropertyName("nextcloud_server_url")]
        public string NextcloudServerUrl { get; set; } = string.Empty;

        [JsonPropertyName("nextcloud_bearer_token")]
        public string NextcloudBearerToken { get; set; } = string.Empty;

        [JsonPropertyName("nextcloud_remote_path")]
        public string NextcloudRemotePath { get; set; } = string.Empty;

        [JsonPropertyName("nextcloud_timeout_seconds")]
        public int NextcloudTimeoutSeconds { get; set; } = 10;
    }
}