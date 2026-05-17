using Microsoft.UI.Dispatching;
using System;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using UTPCalendar.Services;

namespace UTPCalendar.ViewModels
{
    public class AdvancedViewModel : INotifyPropertyChanged
    {
        private readonly ProfileStoreService _profileStore;
        private readonly PythonBackendService _pythonService;
        private readonly DispatcherQueue _dispatcherQueue;
        private bool _isInitializing = true;
        private bool _isBusy;

        public AdvancedViewModel(ProfileStoreService profileStore, PythonBackendService pythonService)
        {
            _profileStore = profileStore;
            _pythonService = pythonService;
            _dispatcherQueue = DispatcherQueue.GetForCurrentThread();
            AvailableMonths = new ObservableCollection<int> { 1, 2, 3 };
        }

        public ObservableCollection<int> AvailableMonths { get; }
        public DateTimeOffset MinSelectableDate => new DateTimeOffset(new DateTime(DateTime.Now.Year, DateTime.Now.Month, 1));
        public DateTimeOffset MaxSelectableDate
        {
            get
            {
                var target = DateTime.Now.AddMonths(2);
                return new DateTimeOffset(new DateTime(target.Year, target.Month, DateTime.DaysInMonth(target.Year, target.Month)));
            }
        }

        private string _defaultUserDisplayName = "Ninguno";
        public string DefaultUserDisplayName
        {
            get => _defaultUserDisplayName;
            set
            {
                if (SetProperty(ref _defaultUserDisplayName, value))
                {
                    OnPropertyChanged(nameof(ShortDisplayName));
                }
            }
        }

        public string ShortDisplayName
        {
            get
            {
                if (string.IsNullOrWhiteSpace(DefaultUserDisplayName) || DefaultUserDisplayName == "Ninguno")
                    return DefaultUserDisplayName;

                var parts = DefaultUserDisplayName.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                return string.Join(" ", parts.Take(2));
            }
        }

        private ImageSource? _defaultUserProfilePicture;
        public ImageSource? DefaultUserProfilePicture { get => _defaultUserProfilePicture; set { if (SetProperty(ref _defaultUserProfilePicture, value)) { OnPropertyChanged(nameof(HasProfilePicture)); OnPropertyChanged(nameof(NoProfilePicture)); } } }

        public Visibility HasProfilePicture => DefaultUserProfilePicture != null ? Visibility.Visible : Visibility.Collapsed;
        public Visibility NoProfilePicture => DefaultUserProfilePicture == null ? Visibility.Visible : Visibility.Collapsed;

        private bool _useCustomDateRange;
        public bool UseCustomDateRange
        {
            get => _useCustomDateRange;
            set { if (SetProperty(ref _useCustomDateRange, value)) { OnPropertyChanged(nameof(IsMonthsModeEnabled)); AutoSave(); } }
        }

        public bool IsMonthsModeEnabled => !UseCustomDateRange;

        private int _searchRangeMonths = 2;
        public int SearchRangeMonths { get => _searchRangeMonths; set { if (SetProperty(ref _searchRangeMonths, value)) AutoSave(); } }

        private DateTimeOffset? _customStartDate;
        public DateTimeOffset? CustomStartDate { get => _customStartDate; set { if (SetProperty(ref _customStartDate, value)) AutoSave(); } }

        private DateTimeOffset? _customEndDate;
        public DateTimeOffset? CustomEndDate { get => _customEndDate; set { if (SetProperty(ref _customEndDate, value)) AutoSave(); } }

        private bool _autostartEnabled;
        public bool AutostartEnabled
        {
            get => _autostartEnabled;
            set
            {
                if (SetProperty(ref _autostartEnabled, value))
                {
                    AutoSave();

                    if (!_isInitializing)
                    {
                        _ = _pythonService.RepairAutorunAsync(value);
                    }
                }
            }
        }

        private string _holidaysStatus = "Cargando...";
        public string HolidaysStatus { get => _holidaysStatus; set => SetProperty(ref _holidaysStatus, value); }

        private string _repairStatusText = "El servicio está funcionando correctamente.";
        public string RepairStatusText { get => _repairStatusText; set => SetProperty(ref _repairStatusText, value); }
        public bool IsBusy { get => _isBusy; private set => SetProperty(ref _isBusy, value); }

        public async Task LoadAsync()
        {
            _isInitializing = true;
            var data = await _profileStore.LoadProfilesAsync().ConfigureAwait(false);
            var defUser = data.Users.FirstOrDefault(u => u.Username == data.Settings.DefaultUsername);

            _dispatcherQueue.TryEnqueue(() =>
            {
                if (defUser != null)
                {
                    DefaultUserDisplayName = string.IsNullOrWhiteSpace(defUser.FullName) ? defUser.Username : defUser.FullName;
                    if (!string.IsNullOrWhiteSpace(defUser.ProfilePicturePath))
                    {
                        try { DefaultUserProfilePicture = new BitmapImage(new Uri(defUser.ProfilePicturePath)); } catch { DefaultUserProfilePicture = null; }
                    }
                    else DefaultUserProfilePicture = null;
                }
                else
                {
                    DefaultUserDisplayName = "Sin usuario";
                    DefaultUserProfilePicture = null;
                }

                UseCustomDateRange = data.Settings.UseCustomDateRange;
                SearchRangeMonths = data.Settings.SearchRangeMonths;
                CustomStartDate = data.Settings.CustomStartDate;
                CustomEndDate = data.Settings.CustomEndDate;
                AutostartEnabled = data.Settings.AutostartEnabled;
                HolidaysStatus = $"Última actualización: {data.Settings.LastHolidaysUpdate}";
                _isInitializing = false;
            });
        }

        private async void AutoSave()
        {
            if (_isInitializing) return;
            var data = await _profileStore.LoadProfilesAsync().ConfigureAwait(false);
            data.Settings.UseCustomDateRange = UseCustomDateRange;
            data.Settings.SearchRangeMonths = SearchRangeMonths;
            data.Settings.CustomStartDate = CustomStartDate;
            data.Settings.CustomEndDate = CustomEndDate;
            data.Settings.AutostartEnabled = AutostartEnabled;
            await _profileStore.SaveProfilesAsync(data).ConfigureAwait(false);
        }

        public Task RefreshHolidaysAsync()
        {
            HolidaysStatus = "Actualizando...";
            IsBusy = true;
            return Task.Run(async () =>
            {
                try
                {
                    var res = await _pythonService.RefreshHolidaysAsync().ConfigureAwait(false);
                    if (res.success)
                    {
                        _dispatcherQueue.TryEnqueue(() => HolidaysStatus = $"Actualizado: {DateTime.Now:dd/MM HH:mm}");
                        var data = await _profileStore.LoadProfilesAsync().ConfigureAwait(false);
                        data.Settings.LastHolidaysUpdate = DateTime.Now.ToString("dd/MM/yyyy HH:mm");
                        await _profileStore.SaveProfilesAsync(data).ConfigureAwait(false);
                    }
                    else
                    {
                        _dispatcherQueue.TryEnqueue(() => HolidaysStatus = res.message);
                    }
                }
                finally
                {
                    _dispatcherQueue.TryEnqueue(() => IsBusy = false);
                }
            });
        }

        public Task RepairAutostartAsync()
        {
            RepairStatusText = "Reparando...";
            IsBusy = true;
            return Task.Run(async () =>
            {
                try
                {
                    var res = await _pythonService.RepairAutorunAsync(AutostartEnabled).ConfigureAwait(false);
                    _dispatcherQueue.TryEnqueue(() => RepairStatusText = res.success ? "Reparado con éxito." : "Error en reparación.");
                }
                finally
                {
                    _dispatcherQueue.TryEnqueue(() => IsBusy = false);
                }
            });
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
        protected bool SetProperty<T>(ref T storage, T value, [CallerMemberName] string? name = null)
        {
            if (Equals(storage, value)) return false;
            storage = value; OnPropertyChanged(name); return true;
        }
    }
}