using System.Text.Json.Serialization;

namespace UTPCalendar.Interop
{
    public class UserProfileDto
    {
        [JsonPropertyName("username")]
        public string Username { get; set; } = string.Empty;

        [JsonPropertyName("password")]
        public string Password { get; set; } = string.Empty;

        [JsonPropertyName("full_name")]
        public string FullName { get; set; } = string.Empty;

        [JsonPropertyName("career")]
        public string Career { get; set; } = string.Empty;

        [JsonPropertyName("modality")]
        public string Modality { get; set; } = string.Empty;

        [JsonPropertyName("campus")]
        public string Campus { get; set; } = string.Empty;

        [JsonPropertyName("email")]
        public string Email { get; set; } = string.Empty;

        [JsonPropertyName("profile_picture_path")]
        public string ProfilePicturePath { get; set; } = string.Empty;
    }
}