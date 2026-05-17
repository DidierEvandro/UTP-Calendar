using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using UTPCalendar.Services;

namespace UTPCalendar.ViewModels
{
    public partial class RemindersViewModel : INotifyPropertyChanged
    {
        private readonly ProfileStoreService _profileStore;
        private bool _isInitializing = true;

        public RemindersViewModel(ProfileStoreService profileStore)
        {
            _profileStore = profileStore;
            _ = LoadAsync();
        }

        private bool _isEnabled;
        public bool IsEnabled
        {
            get => _isEnabled;
            set { if (_isEnabled == value) return; _isEnabled = value; AutoSave(); OnPropertyChanged(); }
        }

        private double _firstEventMinutes;
        public double FirstEventMinutes
        {
            get => _firstEventMinutes;
            set { if (_firstEventMinutes == value) return; _firstEventMinutes = value; AutoSave(); OnPropertyChanged(); }
        }

        private double _otherEventsMinutes;
        public double OtherEventsMinutes
        {
            get => _otherEventsMinutes;
            set { if (_otherEventsMinutes == value) return; _otherEventsMinutes = value; AutoSave(); OnPropertyChanged(); }
        }

        public async Task LoadAsync()
        {
            _isInitializing = true;
            var data = await _profileStore.LoadProfilesAsync();
            IsEnabled = data.Settings.RemindersEnabled;
            FirstEventMinutes = data.Settings.FirstEventReminderMinutes;
            OtherEventsMinutes = data.Settings.OtherEventsReminderMinutes;
            _isInitializing = false;
        }

        private async void AutoSave()
        {
            if (_isInitializing) return;
            var data = await _profileStore.LoadProfilesAsync();
            data.Settings.RemindersEnabled = IsEnabled;
            data.Settings.FirstEventReminderMinutes = (int)FirstEventMinutes;
            data.Settings.OtherEventsReminderMinutes = (int)OtherEventsMinutes;
            await _profileStore.SaveProfilesAsync(data);
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? propertyName = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}