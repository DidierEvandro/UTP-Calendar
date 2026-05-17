using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using System;
using UTPCalendar.ViewModels;

namespace UTPCalendar.View.Pages
{
    public sealed partial class AdvancedPage : Page
    {
        public AdvancedViewModel ViewModel { get; }

        public AdvancedPage()
        {
            ViewModel = MainWindow.Instance.ViewModel.Advanced;
            this.InitializeComponent();
        }

        protected override async void OnNavigatedTo(NavigationEventArgs e)
        {
            base.OnNavigatedTo(e);
            await ViewModel.LoadAsync();

            try
            {
                StartDatePicker.MinDate = ViewModel.MinSelectableDate;
                StartDatePicker.MaxDate = ViewModel.MaxSelectableDate;
                EndDatePicker.MinDate = ViewModel.MinSelectableDate;
                EndDatePicker.MaxDate = ViewModel.MaxSelectableDate;
            }
            catch { }
        }

        private async void RefreshHolidays_Click(object sender, RoutedEventArgs e) => await ViewModel.RefreshHolidaysAsync();
        private async void RepairAutostart_Click(object sender, RoutedEventArgs e) => await ViewModel.RepairAutostartAsync();
    }
}