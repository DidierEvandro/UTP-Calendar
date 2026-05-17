using Microsoft.UI.Dispatching;
using System;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using UTPCalendar.Interop;
using UTPCalendar.Models;
using UTPCalendar.Services;

namespace UTPCalendar.ViewModels
{
    public partial class UsersViewModel : INotifyPropertyChanged
    {
        private readonly ProfileStoreService _profileStore;
        private readonly PythonBackendService _pythonService;
        private readonly LoggingService _loggingService;
        private readonly DispatcherQueue _dispatcherQueue;
        private readonly Stopwatch _executionTimer = new Stopwatch();

        private string _lastGeneratedUrl = "";
        private bool _isBusy;
        private bool _isLoading;
        private string _busyMessage = "";

        public PythonBackendService Backend => _pythonService;
        public ObservableCollection<UserProfile> Users { get; set; } = new();
        public ObservableCollection<UserProfile> FilteredUsers { get; set; } = new();
        public bool IsBusy
        {
            get => _isBusy;
            private set
            {
                if (_isBusy == value) return;
                _isBusy = value;
                OnPropertyChanged();
                OnPropertyChanged(nameof(IsLoading));
            }
        }

        public bool IsLoading
        {
            get => _isLoading;
            private set
            {
                if (_isLoading == value) return;
                _isLoading = value;
                IsBusy = value;
            }
        }

        public string BusyMessage
        {
            get => _busyMessage;
            private set
            {
                if (_busyMessage == value) return;
                _busyMessage = value;
                OnPropertyChanged();
            }
        }

        private UserProfile? _selectedUser;
        public UserProfile? SelectedUser
        {
            get => _selectedUser;
            set
            {
                if (_selectedUser == value) return;
                _selectedUser = value;
                OnPropertyChanged();
            }
        }

        public UsersViewModel(ProfileStoreService profileStore, PythonBackendService pythonService, LoggingService loggingService)
        {
            _profileStore = profileStore;
            _pythonService = pythonService;
            _loggingService = loggingService;
            _dispatcherQueue = DispatcherQueue.GetForCurrentThread();

            _pythonService.LogReceived += (sender, message) =>
            {
                if (message.StartsWith("RESULT_URL:"))
                {
                    _lastGeneratedUrl = message.Substring(11).Trim();
                    return;
                }

                _dispatcherQueue?.TryEnqueue(() =>
                {
                    string timeStamp = DateTime.Now.ToString("HH:mm:ss");
                    _loggingService.Log($"[{timeStamp}] > {message}");
                });
            };

            _ = LoadAsync();
        }

        public async Task LoadAsync()
        {
            var data = await _profileStore.LoadProfilesAsync().ConfigureAwait(false);
            _dispatcherQueue.TryEnqueue(() =>
            {
                Users.Clear();
                FilteredUsers.Clear();
            });

            foreach (var userDto in data.Users)
            {
                var user = new UserProfile
                {
                    Username = userDto.Username ?? "",
                    Password = userDto.Password ?? "",
                    FullName = userDto.FullName ?? "",
                    Career = userDto.Career ?? "",
                    Modality = userDto.Modality ?? "",
                    Campus = userDto.Campus ?? "",
                    Email = userDto.Email ?? "",
                    ProfilePicturePath = userDto.ProfilePicturePath ?? "",
                    IsDefault = userDto.Username == data.Settings.DefaultUsername
                };

                _dispatcherQueue.TryEnqueue(() =>
                {
                    Users.Add(user);
                    FilteredUsers.Add(user);
                });
            }
        }

        public async Task AddUserAsync(string username, string password)
        {
            var newUser = new UserProfile { Username = username, Password = password };
            Users.Add(newUser);
            FilteredUsers.Add(newUser);
            SelectedUser = newUser;
            await SaveUsersAsync().ConfigureAwait(false);

            IsLoading = true;
            BusyMessage = $"Actualizando metadatos de {newUser.Username}...";

            await UpdateUserMetadataAsync(newUser);
        }

        public async Task UpdateUserMetadataAsync(UserProfile user)
        {
            BusyMessage = $"Actualizando metadatos de {user.Username}...";
            IsLoading = true;
            _loggingService.Log($"Iniciando actualización de metadatos para {user.Username}...");

            try
            {
                var (success, profileData, message) = await Task.Run(() => _pythonService.UpdateMetadataAsync(user.Username, user.Password)).ConfigureAwait(false);

                if (success && profileData != null)
                {
                    _dispatcherQueue.TryEnqueue(() =>
                    {
                        user.FullName = profileData.FullName;
                        user.Career = profileData.Career;
                        user.Modality = profileData.Modality;
                        user.Campus = profileData.Campus;
                        user.Email = profileData.Email;
                        user.ProfilePicturePath = profileData.ProfilePicturePath;
                        RefreshView();
                        BusyMessage = "Metadatos actualizados.";
                    });

                    await SaveUsersAsync().ConfigureAwait(false);
                }
                else
                {
                    _dispatcherQueue.TryEnqueue(() => BusyMessage = string.IsNullOrWhiteSpace(message) ? "No se pudieron actualizar los metadatos." : message);
                }
            }
            catch (Exception ex)
            {
                _dispatcherQueue.TryEnqueue(() => BusyMessage = ex.Message);
            }
            finally
            {
                _dispatcherQueue.TryEnqueue(() => IsBusy = false);
            }
        }

        public void FilterUsers(string query)
        {
            FilteredUsers.Clear();
            var filtered = string.IsNullOrWhiteSpace(query)
                ? Users
                : Users.Where(u => u.Username.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                                   u.FullName.Contains(query, StringComparison.OrdinalIgnoreCase));

            foreach (var u in filtered) FilteredUsers.Add(u);
        }

        public void SortUsers(bool ascending)
        {
            var sorted = ascending ? Users.OrderBy(u => u.FullName).ToList() : Users.OrderByDescending(u => u.FullName).ToList();
            Users.Clear();
            foreach (var u in sorted) Users.Add(u);
            RefreshView();
        }

        public async Task SetDefaultUserAsync(UserProfile selectedUser)
        {
            foreach (var user in Users) user.IsDefault = (user == selectedUser);

            var temp = Users.ToList();
            Users.Clear();
            foreach (var u in temp) Users.Add(u);

            var data = await _profileStore.LoadProfilesAsync();
            data.Settings.DefaultUsername = selectedUser.Username;
            await _profileStore.SaveProfilesAsync(data);
            RefreshView();
        }

        public void RemoveUser(UserProfile user)
        {
            Users.Remove(user);
            FilteredUsers.Remove(user);
            _ = SaveUsersAsync();
        }

        public async Task SaveUsersAsync()
        {
            var data = await _profileStore.LoadProfilesAsync();
            data.Users = Users.Select(u => new UserProfileDto
            {
                Username = u.Username,
                Password = u.Password,
                FullName = u.FullName,
                Career = u.Career,
                Modality = u.Modality,
                Campus = u.Campus,
                Email = u.Email,
                ProfilePicturePath = u.ProfilePicturePath
            }).ToList();
            await _profileStore.SaveProfilesAsync(data);
        }

        public void RefreshView() => FilterUsers("");

        public async Task GenerateIcsAsync()
        {
            var user = SelectedUser ?? Users.FirstOrDefault(u => u.IsDefault);
            if (user == null) return;

            BusyMessage = "Generando ICS...";
            IsLoading = true;
            _lastGeneratedUrl = "";
            _executionTimer.Restart();

            try
            {
                await _pythonService.StartAsync().ConfigureAwait(false);
                var (code, message) = await Task.Run(() => _pythonService.RunPipelineAsync(user.Username, user.Password)).ConfigureAwait(true);

                _executionTimer.Stop();

                if (code == 0)
                {
                    _loggingService.Log("Extracción finalizada con éxito.");

                    string displayNames = "Usuario";
                    if (!string.IsNullOrWhiteSpace(user.FullName))
                    {
                        var parts = user.FullName.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                        displayNames = parts.Length >= 2 ? $"{parts[0]} {parts[1]}" : parts[0];
                    }

                    var nowStr = $"{DateTime.Now:dd/MM/yyyy HH:mm} ({displayNames})";
                    var updatedData = await _profileStore.LoadProfilesAsync().ConfigureAwait(false);
                    updatedData.Settings.LastIcsGenerated = nowStr;

                    if (updatedData.Settings.NextcloudUploadEnabled && !string.IsNullOrWhiteSpace(_lastGeneratedUrl))
                    {
                        updatedData.Settings.LastNextcloudUpload = nowStr;
                        updatedData.Settings.SubscriptionIcsUrl = _lastGeneratedUrl;

                        if (MainWindow.Instance?.ViewModel != null)
                        {
                            MainWindow.Instance.ViewModel.Nextcloud.SubscriptionUrl = _lastGeneratedUrl;
                        }
                    }

                    await _profileStore.SaveProfilesAsync(updatedData).ConfigureAwait(false);

                    MainWindow.Instance?.RefreshStatusDates(
                        nowStr,
                        (updatedData.Settings.NextcloudUploadEnabled && !string.IsNullOrWhiteSpace(_lastGeneratedUrl)) ? nowStr : null
                    );
                    BusyMessage = "Extracción finalizada.";
                }
                else
                {
                    _loggingService.Log($"Error: {message}");
                    BusyMessage = message;
                }
            }
            catch (Exception ex)
            {
                BusyMessage = ex.Message;
            }
            finally
            {
                IsBusy = false;
            }
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}