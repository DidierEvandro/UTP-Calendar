using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System;
using System.Threading.Tasks;

namespace UTPCalendar.View.Pages
{
    public sealed partial class CalendarPage : Page
    {
        public ViewModels.CalendarViewModel ViewModel { get; }

        public CalendarPage()
        {
            this.InitializeComponent();
            ViewModel = MainWindow.Instance.ViewModel.Calendar;

            // Nos suscribimos a los cambios del modelo para detectar cambios de usuario/datos
            ViewModel.PropertyChanged -= ViewModel_PropertyChanged;
            ViewModel.PropertyChanged += ViewModel_PropertyChanged;

            _ = ViewModel.LoadAsync();

            if (MainCalendar.SelectedDates.Count == 0)
            {
                MainCalendar.SelectedDates.Add(DateTimeOffset.Now);
            }
        }

        private void ViewModel_PropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
        {
            // Cuando cambia la lista de eventos filtrados (cambio de usuario o recarga de datos)
            // Obligamos al calendario a repintarse simulando lo mismo que el botón "Ir a Hoy"
            if (e.PropertyName == nameof(ViewModel.FilteredEvents))
            {
                DispatcherQueue.TryEnqueue(async () =>
                {
                    DateTimeOffset currentDate = ViewModel.CurrentSelectedDate;

                    // Salto rápido de fechas para forzar la destrucción y re-creación de los colores de los días
                    MainCalendar.SetDisplayDate(currentDate.AddDays(15));
                    await Task.Delay(15); // Una pausa imperceptible para que el sistema dibuje el cambio
                    MainCalendar.SetDisplayDate(currentDate);

                    MainCalendar.SelectedDates.Clear();
                    MainCalendar.SelectedDates.Add(currentDate);
                });
            }
        }

        private async void Refresh_Click(object sender, RoutedEventArgs e)
        {
            await ViewModel.LoadAsync();
        }

        private void GoToToday_Click(object sender, RoutedEventArgs e)
        {
            MainCalendar.SetDisplayDate(DateTimeOffset.Now);
            MainCalendar.SelectedDates.Clear();
            MainCalendar.SelectedDates.Add(DateTimeOffset.Now);
        }

        private void MainCalendar_SelectedDatesChanged(CalendarView sender, CalendarViewSelectedDatesChangedEventArgs args)
        {
            if (args.AddedDates.Count > 0)
            {
                ViewModel.CurrentSelectedDate = args.AddedDates[0].Date;
            }
        }

        private void MainCalendar_CalendarViewDayItemChanging(CalendarView sender, CalendarViewDayItemChangingEventArgs args)
        {
            if (args.Item is null) return;

            var date = args.Item.Date.Date;
            var hasEvents = ViewModel.HasEventsOnDate(date);

            args.Item.SetDensityColors(null);

            var accentColor = (Windows.UI.Color)Application.Current.Resources["SystemAccentColor"];
            var accentBrush = new SolidColorBrush(accentColor);
            var whiteTextBrush = new SolidColorBrush(Colors.White);
            var defaultTextBrush = (Brush)Application.Current.Resources["TextFillColorPrimaryBrush"];

            if (date == DateTime.Today || hasEvents)
            {
                args.Item.Background = accentBrush;
                args.Item.Foreground = whiteTextBrush;
                args.Item.FontWeight = Microsoft.UI.Text.FontWeights.Bold;
            }
            else
            {
                args.Item.Background = null;
                args.Item.Foreground = defaultTextBrush;
                args.Item.FontWeight = Microsoft.UI.Text.FontWeights.Normal;
            }
        }
    }
}