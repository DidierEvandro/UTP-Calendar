using System;
using System.Threading.Tasks;

namespace UTPCalendar.Services
{
    public class NextcloudService
    {
        private readonly PythonBackendService _backend;

        public NextcloudService(PythonBackendService backend)
        {
            _backend = backend;
        }

        public async Task<(bool success, string message)> TestConnectionAsync(string serverUrl, string bearerToken, string remotePath, int timeoutSeconds = 10)
        {
            try
            {
                return await _backend.TestNextcloudAsync(serverUrl, bearerToken, remotePath);
            }
            catch (Exception ex)
            {
                return (false, $"Error al probar Nextcloud: {ex.Message}");
            }
        }
    }
}