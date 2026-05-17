using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System;
using System.Linq;
using System.Threading.Tasks;
using UTPCalendar.Models;
using UTPCalendar.ViewModels;
using Windows.ApplicationModel.DataTransfer;

namespace UTPCalendar.View.Pages
{
    public sealed partial class UsersPage : Page
    {
        public UsersViewModel ViewModel { get; }

        public UsersPage()
        {
            ViewModel = MainWindow.Instance.ViewModel.Users;
            this.InitializeComponent();
        }

        private void SearchBox_TextChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args)
        {
            if (args.Reason == AutoSuggestionBoxTextChangeReason.UserInput)
            {
                ViewModel.FilterUsers(sender.Text);
            }
        }

        private void SortAZ_Click(object sender, RoutedEventArgs e) => ViewModel.SortUsers(true);
        private void SortZA_Click(object sender, RoutedEventArgs e) => ViewModel.SortUsers(false);

        private async void AddUser_Click(object sender, RoutedEventArgs e)
        {
            var usernameBox = new TextBox { PlaceholderText = "Ej. U22200000", Margin = new Thickness(0, 0, 0, 12) };
            var passwordBox = new PasswordBox { PlaceholderText = "Contraseña" };

            var panel = new StackPanel();
            panel.Children.Add(new TextBlock { Text = "Código de Alumno", Margin = new Thickness(0, 0, 0, 4) });
            panel.Children.Add(usernameBox);
            panel.Children.Add(new TextBlock { Text = "Contraseña", Margin = new Thickness(0, 0, 0, 4) });
            panel.Children.Add(passwordBox);

            var dialog = new ContentDialog
            {
                Title = "Agregar nuevo usuario",
                Content = panel,
                PrimaryButtonText = "Agregar",
                CloseButtonText = "Cancelar",
                XamlRoot = this.XamlRoot
            };

            if (await dialog.ShowAsync() == ContentDialogResult.Primary)
            {
                await ViewModel.AddUserAsync(usernameBox.Text, passwordBox.Password);
            }
        }

        private async void InfoUser_Click(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Tag is UserProfile user)
            {
                var stack = new StackPanel { Spacing = 10, HorizontalAlignment = HorizontalAlignment.Left };

                stack.Children.Add(new TextBlock { Text = "Información Académica", FontWeight = Microsoft.UI.Text.FontWeights.Bold, FontSize = 16, Margin = new Thickness(0, 0, 0, 5) });
                stack.Children.Add(new TextBlock { Text = $" Carrera: {user.Career}", TextWrapping = TextWrapping.Wrap });
                stack.Children.Add(new TextBlock { Text = $" Modalidad: {user.Modality}" });
                stack.Children.Add(new TextBlock { Text = $" Sede: {user.Campus}" });
                stack.Children.Add(new TextBlock { Text = $" Correo: {user.Email}", IsTextSelectionEnabled = true });

                var dialog = new ContentDialog
                {
                    Title = $"Detalles de Usuario",
                    Content = stack,
                    CloseButtonText = "Cerrar",
                    XamlRoot = this.XamlRoot
                };

                await dialog.ShowAsync();
            }
        }

        private string GetFirstTwoNames(string fullName)
        {
            if (string.IsNullOrWhiteSpace(fullName)) return "este usuario";
            var parts = fullName.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            return parts.Length >= 2 ? $"{parts[0]} {parts[1]}" : parts[0];
        }

        private async void SetDefault_Click(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Tag is UserProfile user)
            {
                if (user.IsDefault) return;

                string displayNames = GetFirstTwoNames(user.FullName);
                var confirmDialog = new ContentDialog
                {
                    Title = "Cambiar usuario predeterminado",
                    Content = $"¿Deseas establecer a {displayNames} como el usuario principal para el calendario?",
                    PrimaryButtonText = "Sí, establecer",
                    CloseButtonText = "Cancelar",
                    XamlRoot = this.XamlRoot
                };

                if (await confirmDialog.ShowAsync() == ContentDialogResult.Primary)
                {
                    await ViewModel.SetDefaultUserAsync(user);
                }
            }
        }

        private async void UpdateMetadata_Click(object sender, RoutedEventArgs e)
        {
            if (sender is MenuFlyoutItem item && item.Tag is UserProfile user)
            {
                await ViewModel.UpdateUserMetadataAsync(user);
            }
        }

        private async void EditCredentials_Click(object sender, RoutedEventArgs e)
        {
            if (sender is MenuFlyoutItem item && item.Tag is UserProfile user)
            {
                var passwordBox = new PasswordBox { PlaceholderText = "Nueva Contraseña" };
                var dialog = new ContentDialog
                {
                    Title = $"Editar contraseña de {user.Username}",
                    Content = passwordBox,
                    PrimaryButtonText = "Guardar",
                    CloseButtonText = "Cancelar",
                    XamlRoot = this.XamlRoot
                };

                if (await dialog.ShowAsync() == ContentDialogResult.Primary)
                {
                    user.Password = passwordBox.Password;
                    await ViewModel.SaveUsersAsync();
                }
            }
        }

        private async void DeleteUser_Click(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Tag is UserProfile user)
            {
                string displayNames = GetFirstTwoNames(user.FullName);
                var confirmDialog = new ContentDialog
                {
                    Title = "Eliminar Usuario",
                    Content = $"¿Estás seguro de que deseas eliminar a {displayNames}? Esta acción no se puede deshacer.",
                    PrimaryButtonText = "Eliminar",
                    CloseButtonText = "Cancelar",
                    DefaultButton = ContentDialogButton.Close,
                    XamlRoot = this.XamlRoot
                };

                if (await confirmDialog.ShowAsync() == ContentDialogResult.Primary)
                {
                    ViewModel.RemoveUser(user);
                }
            }
        }

        private async void CopyLink_Click(object sender, RoutedEventArgs e)
        {
            // CORRECCIÓN: Ahora evalúa si es Button en lugar de MenuFlyoutItem
            if (sender is Button btn && btn.Tag is UserProfile user)
            {
                var nextcloudVM = MainWindow.Instance.ViewModel.Nextcloud;

                if (!nextcloudVM.IsEnabled)
                {
                    var dialog = new ContentDialog { Title = "Sincronización inactiva", Content = "Debes activar Nextcloud en Ajustes primero.", CloseButtonText = "Entendido", XamlRoot = this.XamlRoot };
                    await dialog.ShowAsync();
                    return;
                }

                nextcloudVM.SelectedUser = user;
                string baseLink = nextcloudVM.GetSubscriptionLink();

                if (string.IsNullOrWhiteSpace(baseLink))
                {
                    var errorDialog = new ContentDialog { Title = "Enlace no generado", Content = "Verifica que la URL del servidor en Nextcloud sea correcta.", CloseButtonText = "Entendido", XamlRoot = this.XamlRoot };
                    await errorDialog.ShowAsync();
                    return;
                }

                // Asegurar que el "/download" no se repita si ya existe
                string directLink = baseLink.EndsWith("/download") ? baseLink : baseLink + "/download";

                var dataPackage = new DataPackage();
                dataPackage.SetText(directLink);
                Clipboard.SetContent(dataPackage);

                var successDialog = new ContentDialog { Title = "Enlace copiado", Content = $"Se copió al portapapeles el link de descarga:\n\n{directLink}", CloseButtonText = "Aceptar", XamlRoot = this.XamlRoot };
                await successDialog.ShowAsync();
            }
        }

        private async void GenerateIcs_Click(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Tag is UserProfile user)
            {
                ViewModel.SelectedUser = user;
                await ViewModel.GenerateIcsAsync();
            }
        }
    }
}