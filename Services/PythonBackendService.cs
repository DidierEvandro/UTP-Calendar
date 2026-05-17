using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace UTPCalendar.Services
{
    public class EmptyParams { }

    public class AuthParams
    {
        public string? username { get; set; }
        public string? password { get; set; }
    }

    public class NextcloudParams
    {
        public string? serverUrl { get; set; }
        public string? bearerToken { get; set; }
        public string? remotePath { get; set; }
    }

    public class RpcRequest<T>
    {
        public int id { get; set; }
        public string? method { get; set; }
        public T? @params { get; set; }
    }

    [JsonSerializable(typeof(JsonElement))]
    [JsonSerializable(typeof(Models.UserProfile))]
    [JsonSerializable(typeof(RpcRequest<EmptyParams>))]
    [JsonSerializable(typeof(RpcRequest<AuthParams>))]
    [JsonSerializable(typeof(RpcRequest<NextcloudParams>))]
    public partial class AppJsonContext : JsonSerializerContext { }

    public partial class PythonBackendService : IDisposable
    {
        private readonly string _pythonExePath;
        private Process? _process;
        private StreamWriter? _stdin;
        private StreamReader? _stdout;
        private StreamReader? _stderr;
        private int _requestIdCounter = 0;
        private readonly object _lockObject = new object();
        private readonly Dictionary<int, TaskCompletionSource<JsonElement>> _pendingRequests = new();
        private bool _disposed = false;

        private static readonly JsonSerializerOptions _jsonOptions = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };
        private static readonly AppJsonContext _jsonContext = new AppJsonContext(_jsonOptions);

        public event EventHandler<string>? LogReceived;
        public event EventHandler<(int percent, string message)>? ProgressUpdated;

        public PythonBackendService()
        {
            var basePath = AppContext.BaseDirectory;
            _pythonExePath = Path.Combine(basePath, "backend", "UTPCalendarBackend.exe");
        }

        public async Task<bool> StartAsync()
        {
            try
            {
                if (_process != null && !_process.HasExited) return true;

                var processInfo = new ProcessStartInfo
                {
                    FileName = _pythonExePath,
                    Arguments = "--rpc",
                    UseShellExecute = false,
                    RedirectStandardInput = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    WorkingDirectory = Path.GetDirectoryName(_pythonExePath)
                };
                processInfo.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                processInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

                _process = Process.Start(processInfo);
                if (_process == null) throw new Exception("No se pudo iniciar el proceso Python");

                _stdin = _process.StandardInput;
                _stdout = _process.StandardOutput;
                _stderr = _process.StandardError;

                _ = Task.Run(ReadOutputLoop);
                _ = Task.Run(ReadErrorLoop);

                await Task.Delay(100).ConfigureAwait(false);
                return await PingAsync().ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                throw new Exception($"Error iniciando backend: {ex.Message}", ex);
            }
        }

        public void Stop()
        {
            try
            {
                var process = _process;
                if (process == null || process.HasExited) return;

                var shutdownRequest = JsonSerializer.Serialize(new RpcRequest<EmptyParams>
                {
                    id = Interlocked.Increment(ref _requestIdCounter),
                    method = "shutdown",
                    @params = new EmptyParams()
                }, typeof(RpcRequest<EmptyParams>), AppJsonContext.Default);

                if (_stdin != null)
                {
                    _stdin.WriteLine(shutdownRequest);
                    _stdin.Flush();
                }

                if (!process.WaitForExit(1000) && !process.HasExited)
                {
                    try
                    {
                        process.Kill(entireProcessTree: true);
                    }
                    catch { }
                }
            }
            catch { }
            finally
            {
                _stdin = null;
                _stdout = null;
                _stderr = null;
                _process = null;
            }
        }

        private bool TryGetPropertyIgnoreCase(JsonElement element, string propertyName, out JsonElement value)
        {
            if (element.ValueKind == JsonValueKind.Object)
            {
                if (element.TryGetProperty(propertyName, out value)) return true;
                foreach (var prop in element.EnumerateObject())
                {
                    if (string.Equals(prop.Name, propertyName, StringComparison.OrdinalIgnoreCase))
                    {
                        value = prop.Value;
                        return true;
                    }
                }
            }
            value = default;
            return false;
        }

        private async Task ReadOutputLoop()
        {
            try
            {
                while (_stdout != null && !_stdout.EndOfStream)
                {
                    var line = await _stdout.ReadLineAsync().ConfigureAwait(false);
                    if (string.IsNullOrEmpty(line)) continue;

                    line = line.Trim();

                    if (line.StartsWith("{") && line.EndsWith("}"))
                    {
                        try
                        {
                            var response = JsonSerializer.Deserialize(line, _jsonContext.JsonElement);

                            if (TryGetPropertyIgnoreCase(response, "method", out var methodElement) && methodElement.GetString() == "progress")
                            {
                                if (TryGetPropertyIgnoreCase(response, "params", out var paramsElement))
                                {
                                    int pct = TryGetPropertyIgnoreCase(paramsElement, "percent", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetInt32() : 0;
                                    string msg = TryGetPropertyIgnoreCase(paramsElement, "message", out var m) ? m.GetString() ?? "" : "";
                                    ProgressUpdated?.Invoke(this, (pct, msg));
                                }
                                continue;
                            }

                            if (TryGetPropertyIgnoreCase(response, "id", out var idElement) && idElement.ValueKind == JsonValueKind.Number && idElement.TryGetInt32(out var id))
                            {
                                lock (_lockObject)
                                {
                                    if (_pendingRequests.TryGetValue(id, out var tcs))
                                    {
                                        _pendingRequests.Remove(id);
                                        tcs.TrySetResult(response);
                                    }
                                }
                            }
                        }
                        catch (JsonException) { LogReceived?.Invoke(this, line); }
                    }
                    else
                    {
                        LogReceived?.Invoke(this, line);
                    }
                }
            }
            catch { }
        }

        private async Task ReadErrorLoop()
        {
            try
            {
                while (_stderr != null && !_stderr.EndOfStream)
                {
                    var line = await _stderr.ReadLineAsync().ConfigureAwait(false);
                    if (!string.IsNullOrEmpty(line)) LogReceived?.Invoke(this, $"[ERROR] {line}");
                }
            }
            catch { }
        }

        public async Task<bool> PingAsync()
        {
            try
            {
                var response = await SendRequest("ping", new EmptyParams()).ConfigureAwait(false);
                return TryGetPropertyIgnoreCase(response, "result", out var result) && result.ValueKind != JsonValueKind.Null;
            }
            catch { return false; }
        }

        private async Task<JsonElement> SendRequest<T>(string method, T parameters)
        {
            if (_process == null || _process.HasExited) await StartAsync().ConfigureAwait(false);
            int requestId;
            lock (_lockObject) { requestId = ++_requestIdCounter; }

            var requestWithId = new RpcRequest<T> { id = requestId, method = method, @params = parameters };
            var json = JsonSerializer.Serialize(requestWithId, typeof(RpcRequest<T>), AppJsonContext.Default);

            var tcs = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
            lock (_lockObject) { _pendingRequests[requestId] = tcs; }

            try
            {
                await _stdin!.WriteLineAsync(json).ConfigureAwait(false);
                await _stdin.FlushAsync().ConfigureAwait(false);

                var completedTask = await Task.WhenAny(tcs.Task, Task.Delay(120000)).ConfigureAwait(false);
                if (completedTask != tcs.Task)
                {
                    lock (_lockObject) { _pendingRequests.Remove(requestId); }
                    throw new TimeoutException($"Timeout esperando respuesta de '{method}' tras 120000 ms.");
                }

                return await tcs.Task.ConfigureAwait(false);
            }
            catch
            {
                lock (_lockObject) { _pendingRequests.Remove(requestId); }
                throw;
            }
        }

        public async Task<(int code, string message)> RunPipelineAsync(string username, string password)
        {
            try
            {
                var response = await SendRequest("run_pipeline", new AuthParams { username = username, password = password }).ConfigureAwait(false);

                if (TryGetPropertyIgnoreCase(response, "result", out var result))
                {
                    var code = TryGetPropertyIgnoreCase(result, "code", out var codeProp) && codeProp.ValueKind == JsonValueKind.Number ? codeProp.GetInt32() : 1;
                    var message = TryGetPropertyIgnoreCase(result, "message", out var msgProp) ? msgProp.GetString() ?? "OK" : "OK";
                    return (code, message);
                }
                return (1, "Error desconocido");
            }
            catch (Exception ex) { return (1, $"Error ejecutando pipeline: {ex.Message}"); }
        }

        public async Task<(bool success, Models.UserProfile? profile, string message)> UpdateMetadataAsync(string username, string password)
        {
            try
            {
                var response = await SendRequest("update_metadata", new AuthParams { username = username, password = password }).ConfigureAwait(false);

                if (TryGetPropertyIgnoreCase(response, "result", out var result))
                {
                    var profileData = JsonSerializer.Deserialize(result.GetRawText(), _jsonContext.UserProfile);
                    return (true, profileData, "OK");
                }
                if (TryGetPropertyIgnoreCase(response, "error", out var error)) return (false, null, error.GetString() ?? "Error");
                return (false, null, "Error");
            }
            catch (Exception ex) { return (false, null, ex.Message); }
        }

        public async Task<(bool success, string message)> TestNextcloudAsync(string serverUrl, string bearerToken, string remotePath)
        {
            try
            {
                var response = await SendRequest("test_nextcloud", new NextcloudParams { serverUrl = serverUrl, bearerToken = bearerToken, remotePath = remotePath }).ConfigureAwait(false);
                if (TryGetPropertyIgnoreCase(response, "result", out var result))
                {
                    var success = TryGetPropertyIgnoreCase(result, "success", out var successProp) && (successProp.ValueKind == JsonValueKind.True || successProp.ValueKind == JsonValueKind.False) ? successProp.GetBoolean() : false;
                    var message = TryGetPropertyIgnoreCase(result, "message", out var msgProp) ? msgProp.GetString() ?? "OK" : "OK";
                    return (success, message);
                }
                return (false, "Error");
            }
            catch (Exception ex) { return (false, ex.Message); }
        }

        public async Task<(bool success, string message)> RefreshHolidaysAsync()
        {
            try
            {
                var response = await SendRequest("refresh_holidays", new EmptyParams()).ConfigureAwait(false);
                if (TryGetPropertyIgnoreCase(response, "result", out var _)) return (true, "OK");
                return (false, "Error");
            }
            catch (Exception ex) { return (false, ex.Message); }
        }

        public async Task<(bool success, string message)> SetAutorunAsync(bool enabled)
        {
            try
            {
                using var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true);
                if (key != null)
                {
                    if (enabled) key.SetValue("UTPCalendar", $"\"{_pythonExePath}\" --autorun");
                    else key.DeleteValue("UTPCalendar", false);
                }
                return await Task.FromResult((true, "OK"));
            }
            catch (Exception ex) { return (false, ex.Message); }
        }

        public async Task<(bool success, string message)> RepairAutorunAsync(bool enabled = true)
        {
            return await SetAutorunAsync(enabled);
        }

        public void Dispose()
        {
            if (_disposed) return;
            Stop();
            _disposed = true;
        }
    }
}