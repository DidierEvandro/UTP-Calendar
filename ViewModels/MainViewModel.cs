using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using UTPCalendar.Services;

namespace UTPCalendar.ViewModels
{
    public class MainViewModel : INotifyPropertyChanged
    {
        private readonly ProfileStoreService _profileStore;

        public UsersViewModel Users { get; }
        public RemindersViewModel Reminders { get; }
        public NextcloudViewModel Nextcloud { get; }
        public CalendarViewModel Calendar { get; }
        public LogsViewModel Logs { get; }
        public AdvancedViewModel Advanced { get; }

        public MainViewModel(
            ProfileStoreService profileStore,
            PythonBackendService pythonBackend,
            CalendarPreviewService calendarPreview,
            NextcloudService nextcloudService,
            HolidayService holidayService,
            LoggingService loggingService)
        {
            _profileStore = profileStore;

            Users = new UsersViewModel(profileStore, pythonBackend, loggingService);
            Reminders = new RemindersViewModel(profileStore);
            Nextcloud = new NextcloudViewModel(profileStore, pythonBackend);
            Calendar = new CalendarViewModel(calendarPreview, profileStore);
            Logs = new LogsViewModel(loggingService);
            Advanced = new AdvancedViewModel(profileStore, pythonBackend);

            _ = pythonBackend.StartAsync();
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void Raise([CallerMemberName] string? name = null) =>
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

        public async Task InitializeAsync()
        {
            await Task.Delay(300);
            await Users.LoadAsync();
            await Calendar.LoadAsync();
            await Nextcloud.LoadAsync();
            await Advanced.LoadAsync();

            var data = await _profileStore.LoadProfilesAsync();
            if (MainWindow.Instance != null)
            {
                MainWindow.Instance.DispatcherQueue.TryEnqueue(() =>
                {
                    MainWindow.Instance.RefreshStatusDates(
                        data.Settings.LastIcsGenerated,
                        data.Settings.NextcloudUploadEnabled ? data.Settings.LastNextcloudUpload : null
                    );
                });
            }
        }
    }
}