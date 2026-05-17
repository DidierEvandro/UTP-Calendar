namespace UTPCalendar.Models
{
    public class AppSettings
    {
        public string LoginUrl { get; set; }
        public string ScheduleUrl { get; set; }
        public bool CycleLockEnabled { get; set; }
        public string SelectedCycle { get; set; }
        public bool RemindersEnabled { get; set; }
        public int FirstEventReminderMinutes { get; set; }
        public int OtherEventsReminderMinutes { get; set; }
        public bool NextcloudUploadEnabled { get; set; }
        public string NextcloudServerUrl { get; set; }
        public string NextcloudBearerToken { get; set; }
        public string NextcloudRemotePath { get; set; }
        public int NextcloudTimeoutSeconds { get; set; }
        public string SubscriptionIcsUrl { get; set; }
        public string DefaultUsername { get; set; }
        public bool AutostartEnabled { get; set; }
        public string DateInputMode { get; set; }
        public string LastIcsGenerated { get; set; }
        public string LastNextcloudUpload { get; set; }
    }
}