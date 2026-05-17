using System;

namespace UTPCalendar.Models
{
    public class CalendarEvent
    {
        public string CourseName { get; set; } = "";
        public string StartTime { get; set; } = "";
        public string EndTime { get; set; } = "";
        public string Location { get; set; } = "";
        public string Type { get; set; } = "";
        public string ReminderText { get; set; } = "";

        // --- NUEVA PROPIEDAD AÑADIDA PARA EL FILTRO DEL CALENDARIO ---
        public DateTime EventDate { get; set; }
    }
}