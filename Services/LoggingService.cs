using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace UTPCalendar.Services
{
    public class LoggingService
    {
        private List<string> _logs = new();
        public event EventHandler<string>? LogAdded;

        public void Log(string message)
        {
            _logs.Add(message);
            LogAdded?.Invoke(this, message);
        }

        // --- SOLUCIÓN AL ERROR CS1061 ---
        // Este alias permite que MainWindow llame a AddLog sin errores
        public void AddLog(string message) => Log(message);

        public Task<List<string>> GetRecentLogsAsync()
        {
            return Task.FromResult(new List<string>(_logs));
        }

        public void ClearAllLogs()
        {
            _logs.Clear();
        }
    }
}