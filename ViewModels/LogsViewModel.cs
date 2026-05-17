using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching;
using UTPCalendar.Services;

namespace UTPCalendar.ViewModels
{
    public partial class LogsViewModel : INotifyPropertyChanged
    {
        private readonly LoggingService _loggingService;
        private readonly DispatcherQueue _dispatcherQueue;

        public ObservableCollection<string> LogMessages { get; } = new();

        public LogsViewModel(LoggingService loggingService)
        {
            _loggingService = loggingService;
            _dispatcherQueue = DispatcherQueue.GetForCurrentThread();
            _loggingService.LogAdded += OnLogAdded;
            _ = LoadAsync();
        }

        public async Task LoadAsync()
        {
            var logs = await _loggingService.GetRecentLogsAsync();
            LogMessages.Clear();
            foreach (var log in logs) LogMessages.Add(log);
        }

        private void OnLogAdded(object? sender, string message)
        {
            _dispatcherQueue?.TryEnqueue(() => LogMessages.Add(message));
        }

        public void ClearLogs()
        {
            LogMessages.Clear();
            _loggingService.ClearAllLogs();
            // Mensaje de sistema tras limpiar
            LogMessages.Add("> Terminal limpia. Esperando nuevos procesos...");
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? name = null) =>
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}