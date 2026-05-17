using System;
using System.Threading.Tasks;
using UTPCalendar.Models;

namespace UTPCalendar.Services
{
    public class AutostartService
    {
        private readonly PythonBackendService _backend;

        public AutostartService(PythonBackendService backend)
        {
            _backend = backend;
        }

        public async Task<AutostartStatus> GetStatusAsync()
        {
            try
            {
                // Aquí se podría enviar una request específica al backend para obtener el estado
                // Por ahora, retorna un estado por defecto
                return new AutostartStatus { Enabled = false, Details = "Estado de autoinicio" };
            }
            catch (Exception ex)
            {
                return new AutostartStatus { Enabled = false, Details = $"Error: {ex.Message}" };
            }
        }

        public async Task<(bool success, string message)> SetAutorunAsync(bool enabled)
        {
            try
            {
                // Aquí se enviaría al backend la request de activar/desactivar autoinicio
                return (true, "Autoinicio actualizado");
            }
            catch (Exception ex)
            {
                return (false, $"Error al cambiar autoinicio: {ex.Message}");
            }
        }

        public async Task<(bool success, string message)> RepairAutorunAsync(bool enabled = true)
        {
            try
            {
                // Aquí se enviaría al backend la request de reparar autoinicio
                return (true, "Autoinicio reparado");
            }
            catch (Exception ex)
            {
                return (false, $"Error al reparar autoinicio: {ex.Message}");
            }
        }
    }
}