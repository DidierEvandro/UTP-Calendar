using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace UTPCalendar.Interop
{
    public class ProfilesDto
    {
        [JsonPropertyName("users")]
        public List<UserProfileDto> Users { get; set; } = new();

        [JsonPropertyName("settings")]
        public SettingsDto Settings { get; set; } = new();
    }
}