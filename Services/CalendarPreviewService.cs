using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Ical.Net;
using UTPCalendar.Models;

namespace UTPCalendar.Services
{
    public class CalendarPreviewService
    {
        public async Task<List<CalendarEvent>> GetEventsAsync(string username)
        {
            return await Task.Run(() =>
            {
                var events = new List<CalendarEvent>();
                string appData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string icsPath = Path.Combine(appData, "UTPCalendar", "data", $"horario_{username}.ics");

                if (!File.Exists(icsPath)) return events;

                try
                {
                    using (var fs = new FileStream(icsPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                    {
                        var calendar = Calendar.Load(fs);
                        foreach (var icalEvent in calendar.Events)
                        {
                            var startDt = icalEvent.Start.Value;
                            var endDt = icalEvent.End.Value;

                            events.Add(new CalendarEvent
                            {
                                CourseName = icalEvent.Summary ?? "Sin nombre",
                                StartTime = startDt.ToString("HH:mm"),
                                EndTime = endDt.ToString("HH:mm"),
                                Location = icalEvent.Location ?? "Por definir",
                                Type = "Clase Programada",
                                EventDate = startDt.Date
                            });
                        }
                    }
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"Error leyendo ICS: {ex.Message}");
                }

                return events.OrderBy(e => e.StartTime).ToList();
            });
        }
    }
}