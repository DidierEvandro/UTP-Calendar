using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.UI.Xaml.Shapes;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.ApplicationModel;
using Windows.ApplicationModel.Activation;
using Windows.Foundation;
using Windows.Foundation.Collections;
using Path = System.IO.Path;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace UTPCalendar
{
    /// <summary>
    /// Provides application-specific behavior to supplement the default Application class.
    /// </summary>
    public partial class App : Application
    {
        private Window? _window;

        /// <summary>
        /// Initializes the singleton application object.  This is the first line of authored code
        /// executed, and as such is the logical equivalent of main() or WinMain().
        /// Se envuelve en try/catch para registrar errores de arranque en log.txt en la carpeta del ejecutable.
        /// </summary>
        public App()
        {
            try
            {
                InitializeComponent();

                // FORZAR IDIOMA ESPAÑOL (PERÚ) GLOBALMENTE
                var culture = new System.Globalization.CultureInfo("es-PE");
                System.Globalization.CultureInfo.CurrentCulture = culture;
                System.Globalization.CultureInfo.CurrentUICulture = culture;
                System.Globalization.CultureInfo.DefaultThreadCurrentCulture = culture;
                System.Globalization.CultureInfo.DefaultThreadCurrentUICulture = culture;

                // Esto asegura que los controles XAML usen el idioma correcto
                Microsoft.Windows.Globalization.ApplicationLanguages.PrimaryLanguageOverride = "es-PE";
            }
            catch (Exception ex)
            {
                try
                {
                    var exeFolder = AppContext.BaseDirectory;
                    var logPath = Path.Combine(exeFolder, "startup-error-log.txt");
                    File.WriteAllText(logPath, DateTime.Now.ToString("s") + " - " + ex.ToString());
                }
                catch { }
#if DEBUG
                var dlg = new Microsoft.UI.Xaml.Controls.ContentDialog()
                {
                    Title = "Error de arranque",
                    Content = ex.ToString(),
                    CloseButtonText = "Cerrar"
                };
                _ = dlg.ShowAsync();
#endif
                throw;
            }
        }

        /// <summary>
        /// Invoked when the application is launched.
        /// </summary>
        /// <param name="args">Details about the launch request and process.</param>
        protected override void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
        {
            try
            {
                _window = new MainWindow();
                _window.Activate();
            }
            catch (Exception ex)
            {
                try
                {
                    var exeFolder = AppContext.BaseDirectory;
                    var logPath = Path.Combine(exeFolder, "startup-error-log.txt");
                    File.WriteAllText(logPath, DateTime.Now.ToString("s") + " - " + ex.ToString());
                }
                catch { }
#if DEBUG
                var dlg = new Microsoft.UI.Xaml.Controls.ContentDialog()
                {
                    Title = "Error de arranque",
                    Content = ex.ToString(),
                    CloseButtonText = "Cerrar"
                };
                _ = dlg.ShowAsync();
#endif
                throw;
            }
        }
    }
}
