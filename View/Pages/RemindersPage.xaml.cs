using Microsoft.UI.Xaml.Controls;
using UTPCalendar.Services;
using UTPCalendar.ViewModels;

namespace UTPCalendar.View.Pages
{
    public sealed partial class RemindersPage : Page
    {
        public RemindersViewModel ViewModel { get; }
        public RemindersPage()
        {
            ViewModel = new RemindersViewModel(new ProfileStoreService());
            this.InitializeComponent();
        }
    }
}