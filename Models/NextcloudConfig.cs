namespace UTPCalendar.Models
{
    public class NextcloudConfig
    {
        public string ServerUrl { get; set; }
        public string BearerToken { get; set; }
        public string RemotePath { get; set; }
        public int TimeoutSeconds { get; set; }
    }
}