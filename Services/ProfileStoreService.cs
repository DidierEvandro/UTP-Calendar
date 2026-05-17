using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using UTPCalendar.Interop;

namespace UTPCalendar.Services
{
    public class ProfileStoreService
    {
        private readonly string _profilePath;
        private readonly string _localAppDataProfilePath;

        public ProfileStoreService()
        {
            // Obtenemos la ruta física REAL de AppData Local
            string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string realLocalAppData = Path.Combine(userProfile, "AppData", "Local");

            _localAppDataProfilePath = Path.Combine(realLocalAppData, "UTPCalendar", "local_profiles.json");
            _profilePath = Path.Combine(AppContext.BaseDirectory, "backend", "local_profiles.json");
        }

        private string GetSafeBasePath()
        {
            string? path = AppDomain.CurrentDomain.BaseDirectory;
            if (string.IsNullOrEmpty(path)) path = AppContext.BaseDirectory;
            if (string.IsNullOrEmpty(path)) path = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
            if (string.IsNullOrEmpty(path)) path = Environment.CurrentDirectory;
            return path ?? string.Empty;
        }

        private JsonSerializerOptions GetJsonOptions() => new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNameCaseInsensitive = true,
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
        };

        public async Task<ProfilesDto> LoadProfilesAsync()
        {
            // FIX: Migración automática a AppData.
            // Si el archivo en LocalAppData no existe, lo copiamos de la carpeta del proyecto.
            // Esto garantiza que Python y C# trabajen SOBRE EL MISMO ARCHIVO físico desde el principio.
            if (!File.Exists(_localAppDataProfilePath))
            {
                try
                {
                    var dir = Path.GetDirectoryName(_localAppDataProfilePath);
                    if (!string.IsNullOrWhiteSpace(dir)) Directory.CreateDirectory(dir);

                    if (File.Exists(_profilePath))
                    {
                        File.Copy(_profilePath, _localAppDataProfilePath, overwrite: false);
                    }
                    else
                    {
                        var defaultJson = JsonSerializer.Serialize(GetDefaultProfiles(), GetJsonOptions());
                        await File.WriteAllTextAsync(_localAppDataProfilePath, defaultJson);
                    }
                }
                catch { }
            }

            string path = File.Exists(_localAppDataProfilePath) ? _localAppDataProfilePath : _profilePath;

            if (!File.Exists(path)) return GetDefaultProfiles();

            try
            {
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var reader = new StreamReader(stream))
                {
                    var json = await reader.ReadToEndAsync();
                    if (string.IsNullOrWhiteSpace(json)) return GetDefaultProfiles();

                    var profiles = JsonSerializer.Deserialize<ProfilesDto>(json, GetJsonOptions());
                    return profiles ?? GetDefaultProfiles();
                }
            }
            catch
            {
                return GetDefaultProfiles();
            }
        }

        public async Task SaveProfilesAsync(ProfilesDto profiles)
        {
            try
            {
                var json = JsonSerializer.Serialize(profiles, GetJsonOptions());

                var localAppDataDir = Path.GetDirectoryName(_localAppDataProfilePath);
                if (!string.IsNullOrWhiteSpace(localAppDataDir)) Directory.CreateDirectory(localAppDataDir);

                await File.WriteAllTextAsync(_localAppDataProfilePath, json);

                // IMPORTANTE: Hemos eliminado el bloque que guardaba en _profilePath.
                // Guardar en la carpeta del proyecto es lo que causaba el riesgo de GitHub
                // y la desincronización de los dos archivos.
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException("Error al guardar perfiles", ex);
            }
        }

        private ProfilesDto GetDefaultProfiles() => new ProfilesDto { Users = new List<UserProfileDto>(), Settings = GetDefaultSettings() };

        private SettingsDto GetDefaultSettings() => new SettingsDto
        {
            UseCustomDateRange = false,
            SearchRangeMonths = 2,
            LoginUrl = "https://sso.utp.edu.pe/auth/realms/Xpedition/protocol/openid-connect/auth?client_id=utpmas-web&redirect_uri=https%3A%2F%2Fportal.utp.edu.pe%2F&response_mode=fragment&response_type=code&scope=openid",
            ScheduleUrl = "https://portal.utp.edu.pe/calendario",
            RemindersEnabled = true,
            FirstEventReminderMinutes = 120,
            OtherEventsReminderMinutes = 5,
            NextcloudUploadEnabled = false,
            NextcloudServerUrl = "",
            NextcloudBearerToken = "",
            NextcloudRemotePath = "",
            NextcloudTimeoutSeconds = 10,
            SubscriptionIcsUrl = "",
            DefaultUsername = "",
            AutostartEnabled = false,
            DateInputMode = "dropdown",
            LastIcsGenerated = "Nunca",
            LastNextcloudUpload = "Nunca",
            LastHolidaysUpdate = "Nunca"
        };
    }
}