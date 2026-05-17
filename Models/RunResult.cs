namespace UTPCalendar.Models
{
    public class RunResult
    {
        public int ExitCode { get; set; }
        public string Message { get; set; }
        public bool Success => ExitCode == 0;
    }
}