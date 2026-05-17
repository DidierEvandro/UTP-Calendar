using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Collections.Specialized;
using UTPCalendar.ViewModels;
using Windows.ApplicationModel.DataTransfer;

namespace UTPCalendar.View.Pages
{
    public sealed partial class LogsPage : Page
    {
        public LogsViewModel ViewModel { get; }

        public LogsPage()
        {
            ViewModel = MainWindow.Instance.ViewModel.Logs;
            this.InitializeComponent();
            ViewModel.LogMessages.CollectionChanged += LogMessages_CollectionChanged;
        }

        private void LogMessages_CollectionChanged(object? sender, NotifyCollectionChangedEventArgs e)
        {
            if (e.Action == NotifyCollectionChangedAction.Add && e.NewItems != null)
            {
                var lastItem = e.NewItems[e.NewItems.Count - 1];
                TerminalListView.ScrollIntoView(lastItem);
            }
        }

        private void ClearLogs_Click(object sender, RoutedEventArgs e) => ViewModel.ClearLogs();

        private async void CopyLogs_Click(object sender, RoutedEventArgs e)
        {
            var allLogs = string.Join(Environment.NewLine, ViewModel.LogMessages);
            if (!string.IsNullOrWhiteSpace(allLogs))
            {
                var dataPackage = new DataPackage();
                dataPackage.SetText(allLogs);
                Clipboard.SetContent(dataPackage);

                ContentDialog dialog = new ContentDialog
                {
                    Title = "Historial copiado",
                    Content = "Los logs se han copiado al portapapeles.",
                    CloseButtonText = "Aceptar",
                    XamlRoot = this.XamlRoot
                };
                await dialog.ShowAsync();
            }
        }
    }
}