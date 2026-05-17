using System.Text.Json.Serialization;

namespace UTPCalendar.Interop
{
    public class BackendRequest
    {
        [JsonPropertyName("method")]
        public string Method { get; set; }

        [JsonPropertyName("params")]
        public object Params { get; set; }
    }

    public class BackendResponse<T>
    {
        [JsonPropertyName("success")]
        public bool Success { get; set; }

        [JsonPropertyName("data")]
        public T Data { get; set; }

        [JsonPropertyName("error")]
        public string Error { get; set; }
    }

    public class RunPipelineRequest
    {
        [JsonPropertyName("username")]
        public string Username { get; set; }

        [JsonPropertyName("password")]
        public string Password { get; set; }

        [JsonPropertyName("login_url")]
        public string LoginUrl { get; set; }

        [JsonPropertyName("schedule_url")]
        public string ScheduleUrl { get; set; }

        [JsonPropertyName("cycle_name")]
        public string CycleName { get; set; }

        [JsonPropertyName("start_date")]
        public string StartDate { get; set; }

        [JsonPropertyName("end_date")]
        public string EndDate { get; set; }

        [JsonPropertyName("reminders_enabled")]
        public bool RemindersEnabled { get; set; }

        [JsonPropertyName("first_reminder_minutes")]
        public int FirstReminderMinutes { get; set; }

        [JsonPropertyName("other_reminder_minutes")]
        public int OtherReminderMinutes { get; set; }

        [JsonPropertyName("nextcloud_enabled")]
        public bool NextcloudEnabled { get; set; }

        [JsonPropertyName("nextcloud_server_url")]
        public string NextcloudServerUrl { get; set; }

        [JsonPropertyName("nextcloud_bearer_token")]
        public string NextcloudBearerToken { get; set; }

        [JsonPropertyName("nextcloud_remote_path")]
        public string NextcloudRemotePath { get; set; }

        [JsonPropertyName("nextcloud_timeout_seconds")]
        public int NextcloudTimeoutSeconds { get; set; }
    }

    public class TestNextcloudRequest
    {
        [JsonPropertyName("server_url")]
        public string ServerUrl { get; set; }

        [JsonPropertyName("bearer_token")]
        public string BearerToken { get; set; }

        [JsonPropertyName("remote_path")]
        public string RemotePath { get; set; }

        [JsonPropertyName("timeout_seconds")]
        public int TimeoutSeconds { get; set; }
    }

    public class TestNextcloudResponse
    {
        [JsonPropertyName("success")]
        public bool Success { get; set; }

        [JsonPropertyName("message")]
        public string Message { get; set; }
    }

    public class AutostartCommandRequest
    {
        [JsonPropertyName("enabled")]
        public bool Enabled { get; set; }
    }

    public class HolidaysRefreshResponse
    {
        [JsonPropertyName("success")]
        public bool Success { get; set; }

        [JsonPropertyName("updated_at")]
        public string UpdatedAt { get; set; }
    }
}