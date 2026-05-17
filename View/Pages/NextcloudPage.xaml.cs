using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using UTPCalendar.ViewModels;
using UTPCalendar.Services;
using System;

namespace UTPCalendar.View.Pages
{
    public sealed partial class NextcloudPage : Page
    {
        public NextcloudViewModel ViewModel { get; }

        public NextcloudPage()
        {
            // Usamos la instancia global del ViewModel para mantener la sincronización con la barra de progreso
            ViewModel = MainWindow.Instance.ViewModel.Nextcloud;
            this.InitializeComponent();
            Loaded += async (_, __) => await ViewModel.LoadAsync();
        }

        private async void TestConnection_Click(object sender, RoutedEventArgs e)
        {
            var (success, message) = await ViewModel.TestConnectionAsync();

            ContentDialog dialog = new ContentDialog
            {
                Title = success ? "Conexión Exitosa" : "Detalles de Conexión",
                Content = message,
                CloseButtonText = "Aceptar",
                XamlRoot = this.XamlRoot
            };
            await dialog.ShowAsync();
        }

        // CORRECCIÓN: Método restaurado para el botón Guardar
        // En NextcloudPage.xaml.cs
        private async void Save_Click(object sender, RoutedEventArgs e)
        {
            await ViewModel.SaveAsync();

            // Opcional: Mostrar un aviso de éxito
            ContentDialog dialog = new ContentDialog
            {
                Title = "Guardado",
                Content = "Configuración de Nextcloud actualizada.",
                CloseButtonText = "Aceptar",
                XamlRoot = this.XamlRoot
            };
            await dialog.ShowAsync();
        }
    }
}