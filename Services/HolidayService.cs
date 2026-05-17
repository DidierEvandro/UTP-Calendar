using System;
using System.Threading.Tasks;

namespace UTPCalendar.Services
{
    public class HolidayService
    {
        private readonly PythonBackendService _backend;

        public HolidayService(PythonBackendService backend)
        {
            _backend = backend;
        }

        public async Task<(bool success, string updatedAt)> RefreshHolidaysCacheAsync()
        {
            try
            {
                var (success, message) = await _backend.RefreshHolidaysAsync();
                return (success, success ? DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") : message);
            }
            catch (Exception ex)
            {
                return (false, $"Error: {ex.Message}");
            }
        }
    }
}