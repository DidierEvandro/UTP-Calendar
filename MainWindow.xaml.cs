using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System;
using System.Linq;
using System.Threading.Tasks;
using UTPCalendar.Services;
using UTPCalendar.ViewModels;

namespace UTPCalendar
{
    public sealed partial class MainWindow : Window
    {
        public static MainWindow Instance { get; private set; }
        public MainViewModel ViewModel { get; }

        private readonly ProfileStoreService _profileStore;
        private readonly PythonBackendService _pythonBackend;

        public MainWindow()
        {
            this.InitializeComponent();
            Instance = this;

            this.SystemBackdrop = new MicaBackdrop();
            ConfigureTitleBar();

            IntPtr hWnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            var windowId = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(hWnd);
            var appWindow = Microsoft.UI.Windowing.AppWindow.GetFromWindowId(windowId);

            if (appWindow != null)
            {
                string iconPath = System.IO.Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico");
                if (System.IO.File.Exists(iconPath))
                {
                    appWindow.SetIcon(iconPath);
                }
            }

            _profileStore = new ProfileStoreService();
            _pythonBackend = new PythonBackendService();
            var calendarPreview = new CalendarPreviewService();
            var nextcloudService = new NextcloudService(_pythonBackend);
            var holidayService = new HolidayService(_pythonBackend);
            var loggingService = new LoggingService();

            ViewModel = new MainViewModel(_profileStore, _pythonBackend, calendarPreview, nextcloudService, holidayService, loggingService);

            _pythonBackend.ProgressUpdated += PythonBackend_ProgressUpdated;

            DispatcherQueue.TryEnqueue(() =>
            {
                var usersItem = NavView.MenuItems.OfType<NavigationViewItem>().FirstOrDefault(i => i.Tag?.ToString() == "users");
                if (usersItem != null) NavView.SelectedItem = usersItem;
                ContentFrame.Navigate(typeof(View.Pages.UsersPage));
            });

            if (this.Content is FrameworkElement rootElement)
            {
                rootElement.Loaded += RootElement_Loaded;
            }

            this.Activated += MainWindow_Activated;

            this.Closed += MainWindow_Closed;
        }

        private void MainWindow_Closed(object sender, WindowEventArgs args)
        {
            if (_pythonBackend != null)
            {
                _pythonBackend.ProgressUpdated -= PythonBackend_ProgressUpdated;
                _pythonBackend.Stop();
                _pythonBackend.Dispose();
            }
        }

        private async void RootElement_Loaded(object sender, RoutedEventArgs e)
        {
            if (sender is FrameworkElement rootElement)
            {
                rootElement.Loaded -= RootElement_Loaded;
            }

            await CheckAndInstallDependenciesAsync();
            await InitializeAppAsync();
        }

        private async Task CheckAndInstallDependenciesAsync()
        {
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string utpFolder = System.IO.Path.Combine(localAppData, "UTPCalendar");
            string lockFile = System.IO.Path.Combine(utpFolder, "browsers_installed.lock");

            string exePath = System.IO.Path.Combine(AppContext.BaseDirectory, "backend", "UTPCalendarBackend.exe");

            if (System.IO.File.Exists(lockFile) || !System.IO.File.Exists(exePath)) return;

            await Task.Delay(500);

            var stackPanel = new StackPanel { Spacing = 15 };
            stackPanel.Children.Add(new TextBlock
            {
                Text = "Estamos configurando el motor seguro para conectar con la universidad. Esta descarga ocurre solo una vez y puede tardar un par de minutos, por favor no cierres la aplicación...",
                TextWrapping = TextWrapping.Wrap
            });

            var progressBar = new ProgressBar { Minimum = 0, Maximum = 100, Value = 0, IsIndeterminate = true };
            stackPanel.Children.Add(progressBar);

            var statusText = new TextBlock { Text = "Iniciando instalación...", FontSize = 12, Opacity = 0.7, TextWrapping = TextWrapping.Wrap };
            stackPanel.Children.Add(statusText);

            var dialog = new ContentDialog
            {
                XamlRoot = this.Content.XamlRoot,
                Title = "Descargando dependencias...",
                Content = stackPanel
            };

            var showTask = dialog.ShowAsync();

            await Task.Delay(150);

            bool hasError = false;

            try
            {
                var processInfo = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = exePath,
                    Arguments = "--install-browsers",
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    CreateNoWindow = true,
                    WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
                };

                using var process = System.Diagnostics.Process.Start(processInfo);
                if (process != null)
                {
                    await Task.Run(async () =>
                    {
                        while (true)
                        {
                            var line = await process.StandardOutput.ReadLineAsync();
                            if (line == null) break;

                            if (string.IsNullOrEmpty(line)) continue;

                            try
                            {
                                var json = System.Text.Json.JsonDocument.Parse(line);
                                if (json.RootElement.TryGetProperty("method", out var method) && method.GetString() == "progress")
                                {
                                    var pct = json.RootElement.GetProperty("params").GetProperty("percent").GetInt32();
                                    var msg = json.RootElement.GetProperty("params").GetProperty("message").GetString();

                                    DispatcherQueue.TryEnqueue(() =>
                                    {
                                        progressBar.IsIndeterminate = false;
                                        progressBar.Value = pct;
                                        statusText.Text = msg;
                                    });
                                }
                            }
                            catch
                            {
                                DispatcherQueue.TryEnqueue(() => statusText.Text = line);
                            }
                        }
                    });

                    await process.WaitForExitAsync();

                    if (process.ExitCode == 0)
                    {
                        if (!System.IO.Directory.Exists(utpFolder))
                        {
                            System.IO.Directory.CreateDirectory(utpFolder);
                        }
                        System.IO.File.WriteAllText(lockFile, "OK");
                    }
                    else
                    {
                        hasError = true;
                        DispatcherQueue.TryEnqueue(() => statusText.Text = $"Error: El proceso de Python falló con código {process.ExitCode}");
                    }
                }
            }
            catch (Exception ex)
            {
                hasError = true;
                DispatcherQueue.TryEnqueue(() => statusText.Text = "Error Crítico C#: " + ex.Message);
            }

            if (hasError)
            {
                await Task.Delay(10000);
            }
            else
            {
                await Task.Delay(1000);
            }

            dialog.Hide();
        }

        private async Task InitializeAppAsync()
        {
            await ViewModel.InitializeAsync();
        }

        private async void MainWindow_Activated(object sender, WindowActivatedEventArgs args)
        {
            if (args.WindowActivationState != WindowActivationState.Deactivated)
            {
                try
                {
                    var profiles = await _profileStore.LoadProfilesAsync();
                    if (profiles?.Settings != null)
                    {
                        string lastIcs = profiles.Settings.LastIcsGenerated ?? "Nunca";
                        string lastNc = profiles.Settings.LastNextcloudUpload ?? "Nunca";
                        RefreshStatusDates(lastIcs, lastNc);
                    }
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"Error: {ex.Message}");
                }
            }
        }

        private void ConfigureTitleBar()
        {
            if (AppWindowTitleBar.IsCustomizationSupported())
            {
                var titleBar = this.AppWindow.TitleBar;
                titleBar.ExtendsContentIntoTitleBar = true;
                titleBar.ButtonBackgroundColor = Colors.Transparent;
                titleBar.ButtonInactiveBackgroundColor = Colors.Transparent;
            }
        }

        private void NavView_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
        {
            if (args.SelectedItemContainer is not NavigationViewItem selectedItem) return;

            var tag = selectedItem.Tag?.ToString();

            if (tag == "settings")
            {
                RotateSettingsIconStoryboard.Begin();
            }

            var targetPage = tag switch
            {
                "users" => typeof(View.Pages.UsersPage),
                "reminders" => typeof(View.Pages.RemindersPage),
                "nextcloud" => typeof(View.Pages.NextcloudPage),
                "logs" => typeof(View.Pages.LogsPage),
                "calendar" => typeof(View.Pages.CalendarPage),
                "help" => typeof(View.Pages.HelpPage),
                "settings" => typeof(View.Pages.AdvancedPage),
                _ => null,
            };

            if (targetPage is null || ContentFrame?.CurrentSourcePageType == targetPage) return;

            ContentFrame.Navigate(targetPage);
        }

        private void NavView_ItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
        {
            if (args.InvokedItemContainer is not NavigationViewItem invokedItem) return;

            var tag = invokedItem.Tag?.ToString();
            if (tag != "settings") return;

            RotateSettingsIconStoryboard.Begin();
        }

        private void SettingsItem_PointerPressed(object sender, Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e)
        {
            RotateSettingsIconStoryboard.Begin();
        }

        private void PythonBackend_ProgressUpdated(object? sender, (int percent, string message) e)
        {
            DispatcherQueue.TryEnqueue(() =>
            {
                MainProgressBar.Value = e.percent;
                ProgressPercentText.Text = $"{e.percent}%";
                StatusText.Text = e.message;
            });
        }

        public void RefreshStatusDates(string lastIcs, string? lastNextcloud)
        {
            DispatcherQueue.TryEnqueue(() =>
            {
                LastIcsText.Text = lastIcs;
                if (lastNextcloud != null) LastNextcloudText.Text = lastNextcloud;
            });
        }
    }
}