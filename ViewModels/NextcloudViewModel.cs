using Microsoft.UI.Dispatching;
using System;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using UTPCalendar.Models;
using UTPCalendar.Services;

namespace UTPCalendar.ViewModels
{
    public class NextcloudViewModel : INotifyPropertyChanged
    {
        private readonly ProfileStoreService _profileStore;
        private readonly PythonBackendService _pythonService;
        private readonly DispatcherQueue _dispatcherQueue;
        private bool _isInitializing = true;
        private bool _isBusy;
        private string _statusMessage = "";

        public ObservableCollection<UserProfile> Users { get; } = new();

        public bool IsBusy { get => _isBusy; private set { if (SetProperty(ref _isBusy, value)) PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(StatusMessage))); } }
        public string StatusMessage { get => _statusMessage; private set => SetProperty(ref _statusMessage, value); }

        private UserProfile? _selectedUser;
        public UserProfile? SelectedUser { get => _selectedUser; set { SetProperty(ref _selectedUser, value); } }

        public NextcloudViewModel(ProfileStoreService profileStore, PythonBackendService pythonService)
        {
            _profileStore = profileStore;
            _pythonService = pythonService;
            _dispatcherQueue = DispatcherQueue.GetForCurrentThread();
            _ = LoadAsync();
        }

        private bool _isEnabled;
        public bool IsEnabled { get => _isEnabled; set { if (SetProperty(ref _isEnabled, value)) AutoSave(); } }

        private string _serverUrl = "";
        public string ServerUrl { get => _serverUrl; set { if (SetProperty(ref _serverUrl, value)) AutoSave(); } }

        private string _token = "";
        public string Token { get => _token; set { if (SetProperty(ref _token, value)) AutoSave(); } }

        private string _remotePath = "";
        public string RemotePath { get => _remotePath; set { if (SetProperty(ref _remotePath, value)) AutoSave(); } }

        private double _timeout = 10;
        public double Timeout { get => _timeout; set { if (SetProperty(ref _timeout, value)) AutoSave(); } }

        private string _subscriptionUrl = "";
        public string SubscriptionUrl { get => _subscriptionUrl; set { if (SetProperty(ref _subscriptionUrl, value)) AutoSave(); } }

        public async Task LoadAsync()
        {
            _isInitializing = true;
            var data = await _profileStore.LoadProfilesAsync().ConfigureAwait(false);
            _dispatcherQueue.TryEnqueue(() =>
            {
                IsEnabled = data.Settings.NextcloudUploadEnabled;
                ServerUrl = data.Settings.NextcloudServerUrl;
                Token = data.Settings.NextcloudBearerToken;
                RemotePath = data.Settings.NextcloudRemotePath;
                Timeout = data.Settings.NextcloudTimeoutSeconds;
                SubscriptionUrl = data.Settings.SubscriptionIcsUrl;

                Users.Clear();
                foreach (var u in data.Users)
                {
                    Users.Add(new UserProfile { Username = u.Username ?? "", FullName = u.FullName ?? "", ProfilePicturePath = u.ProfilePicturePath ?? "", Password = u.Password ?? "" });
                }
                SelectedUser = Users.FirstOrDefault(u => u.Username == data.Settings.DefaultUsername) ?? Users.FirstOrDefault();
                _isInitializing = false;
            });
        }

        private async void AutoSave()
        {
            if (_isInitializing) return;
            await SaveAsync().ConfigureAwait(false);
        }

        public async Task SaveAsync()
        {
            var data = await _profileStore.LoadProfilesAsync().ConfigureAwait(false);
            data.Settings.NextcloudUploadEnabled = IsEnabled;
            data.Settings.NextcloudServerUrl = ServerUrl;
            data.Settings.NextcloudBearerToken = Token;
            data.Settings.NextcloudRemotePath = RemotePath;
            data.Settings.NextcloudTimeoutSeconds = (int)Timeout;
            data.Settings.SubscriptionIcsUrl = SubscriptionUrl;
            await _profileStore.SaveProfilesAsync(data).ConfigureAwait(false);
        }

        public Task<(bool success, string message)> TestConnectionAsync()
        {
            StatusMessage = "Probando conexión...";
            IsBusy = true;
            return Task.Run(async () =>
            {
                try
                {
                    await _pythonService.StartAsync().ConfigureAwait(false);
                    var result = await _pythonService.TestNextcloudAsync(ServerUrl, Token, RemotePath).ConfigureAwait(false);
                    _dispatcherQueue.TryEnqueue(() => StatusMessage = result.success ? "Conexión correcta." : result.message);
                    return result;
                }
                finally
                {
                    _dispatcherQueue.TryEnqueue(() => IsBusy = false);
                }
            });
        }

        public Task GenerateIcsAsync()
        {
            if (SelectedUser == null) return Task.CompletedTask;
            StatusMessage = "Generando ICS...";
            IsBusy = true;

            return Task.Run(async () =>
            {
                try
                {
                    await _pythonService.StartAsync().ConfigureAwait(false);
                    await _pythonService.RunPipelineAsync(SelectedUser.Username, SelectedUser.Password).ConfigureAwait(false);
                    _dispatcherQueue.TryEnqueue(() => StatusMessage = "Generación completada.");
                }
                finally
                {
                    _dispatcherQueue.TryEnqueue(() => IsBusy = false);
                }
            });
        }

        public string GetSubscriptionLink()
        {
            if (string.IsNullOrWhiteSpace(SubscriptionUrl)) return string.Empty;
            return SubscriptionUrl;
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected bool SetProperty<T>(ref T storage, T value, [CallerMemberName] string propertyName = null)
        {
            if (Equals(storage, value)) return false;
            storage = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
            return true;
        }
    }
}