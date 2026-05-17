using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using UTPCalendar.Models;
using UTPCalendar.Services;

namespace UTPCalendar.ViewModels
{
    public partial class CalendarViewModel : INotifyPropertyChanged
    {
        private readonly CalendarPreviewService _calendarService;
        private readonly ProfileStoreService _profileStore;
        private List<CalendarEvent> _allEvents = new();

        private bool _remindersEnabled = true;
        private int _firstEventReminderMinutes = 120;
        private int _otherEventsReminderMinutes = 5;

        public ObservableCollection<CalendarEvent> FilteredEvents { get; } = new();
        public ObservableCollection<UserProfile> Users { get; } = new();

        private DateTime _currentSelectedDate = DateTime.Today;
        public DateTime CurrentSelectedDate
        {
            get => _currentSelectedDate;
            set
            {
                if (_currentSelectedDate != value)
                {
                    _currentSelectedDate = value;
                    FilterEventsForDate(value);
                    OnPropertyChanged();
                }
            }
        }

        private UserProfile? _selectedUser;
        public UserProfile? SelectedUser
        {
            get => _selectedUser;
            set
            {
                // Evitamos dobles ejecuciones si se elige al mismo usuario
                if (_selectedUser?.Username == value?.Username) return;

                _selectedUser = value;
                OnPropertyChanged();
                OnPropertyChanged(nameof(SelectedUserShortName));

                // Disparamos la recarga al cambiar la selección en la lista
                _ = ReloadScheduleAsync();
            }
        }

        public string SelectedUserShortName
        {
            get
            {
                if (_selectedUser == null || string.IsNullOrWhiteSpace(_selectedUser.FullName)) return "Seleccione usuario";
                var parts = _selectedUser.FullName.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                return parts.Length > 1 ? $"{parts[0]} {parts[1]}" : parts[0];
            }
        }

        private bool _isLoading;
        public bool IsLoading
        {
            get => _isLoading;
            set { if (_isLoading == value) return; _isLoading = value; OnPropertyChanged(); }
        }

        private string _selectedDateText = "Agenda del Día";
        public string SelectedDateText
        {
            get => _selectedDateText;
            set { if (_selectedDateText == value) return; _selectedDateText = value; OnPropertyChanged(); }
        }

        public Microsoft.UI.Xaml.Visibility IsEmptyDay => FilteredEvents.Count == 0 ? Microsoft.UI.Xaml.Visibility.Visible : Microsoft.UI.Xaml.Visibility.Collapsed;

        public CalendarViewModel(CalendarPreviewService calendarService, ProfileStoreService profileStore)
        {
            _calendarService = calendarService;
            _profileStore = profileStore;
        }

        public async Task LoadAsync()
        {
            _isReloading = false;
            IsLoading = true;
            try
            {
                var profiles = await _profileStore.LoadProfilesAsync();

                var targetUsername = _selectedUser?.Username ?? profiles.Settings.DefaultUsername;

                Users.Clear();
                foreach (var uDto in profiles.Users)
                {
                    Users.Add(new UserProfile { Username = uDto.Username ?? "", FullName = uDto.FullName ?? "", ProfilePicturePath = uDto.ProfilePicturePath ?? "" });
                }

                _remindersEnabled = profiles.Settings.RemindersEnabled;
                _firstEventReminderMinutes = profiles.Settings.FirstEventReminderMinutes;
                _otherEventsReminderMinutes = profiles.Settings.OtherEventsReminderMinutes;

                var userToSelect = Users.FirstOrDefault(u => u.Username == targetUsername) ?? Users.FirstOrDefault();

                if (userToSelect != null)
                {
                    _selectedUser = userToSelect;
                    OnPropertyChanged(nameof(SelectedUser));
                    OnPropertyChanged(nameof(SelectedUserShortName));

                    await ReloadScheduleAsync();
                }
            }
            finally
            {
                IsLoading = false;
            }
        }

        private bool _isReloading = false;
        public async Task ReloadScheduleAsync()
        {
            if (SelectedUser == null || _isReloading) return;

            _isReloading = true;
            IsLoading = true;

            try
            {
                // Limpiamos totalmente la memoria para que no se mezclen clases
                _allEvents.Clear();
                FilteredEvents.Clear();

                var newEvents = await _calendarService.GetEventsAsync(SelectedUser.Username);
                _allEvents.AddRange(newEvents);

                FilterEventsForDate(CurrentSelectedDate);

                // Este OnPropertyChanged será la señal clave para repintar el calendario visualmente
                OnPropertyChanged(nameof(FilteredEvents));
                OnPropertyChanged(nameof(IsEmptyDay));
            }
            finally
            {
                IsLoading = false;
                _isReloading = false;
            }
        }

        public void FilterEventsForDate(DateTime date)
        {
            FilteredEvents.Clear();
            SelectedDateText = date.ToString("dddd, d 'de' MMMM 'de' yyyy", new CultureInfo("es-PE"));
            SelectedDateText = char.ToUpper(SelectedDateText[0]) + SelectedDateText.Substring(1);

            var daysEvents = _allEvents.Where(e => e.EventDate.Date == date.Date).OrderBy(e => e.StartTime).ToList();

            var isFirst = true;
            foreach (var ev in daysEvents)
            {
                ev.ReminderText = BuildReminderText(isFirst ? _firstEventReminderMinutes : _otherEventsReminderMinutes);
                FilteredEvents.Add(ev);
                isFirst = false;
            }

            OnPropertyChanged(nameof(IsEmptyDay));
            OnPropertyChanged(nameof(FilteredEvents)); // Notifica el cambio al calendario visual
        }

        public bool HasEventsOnDate(DateTime date) => _allEvents.Any(e => e.EventDate.Date == date.Date);

        private string BuildReminderText(int minutes)
        {
            if (!_remindersEnabled) return "Recordatorios desactivados";
            if (minutes <= 0) return "Recordatorio: en el inicio";
            return $"Recordatorio: {minutes} min antes";
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}