using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization; // <-- LIBRERÍA AÑADIDA
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Controls;

namespace UTPCalendar.Models
{
    public class UserProfile : INotifyPropertyChanged
    {
        private string _fullName = string.Empty;
        public string FullName
        {
            get => _fullName;
            set { if (_fullName != value) { _fullName = value; OnPropertyChanged(); } }
        }

        private string _username = string.Empty;
        public string Username
        {
            get => _username;
            set { if (_username != value) { _username = value; OnPropertyChanged(); } }
        }

        private string _password = string.Empty;
        public string Password { get; set; } = string.Empty;

        private bool _isDefault = false;
        public bool IsDefault
        {
            get => _isDefault;
            set
            {
                if (_isDefault != value)
                {
                    _isDefault = value;
                    OnPropertyChanged();
                    OnPropertyChanged(nameof(DefaultStarForeground));
                    OnPropertyChanged(nameof(FavoriteSymbol));
                }
            }
        }

        public string Career { get; set; } = string.Empty;
        public string Modality { get; set; } = string.Empty;
        public string Campus { get; set; } = string.Empty;
        public string Email { get; set; } = string.Empty;

        private string _profilePicturePath = string.Empty;
        public string ProfilePicturePath
        {
            get => _profilePicturePath;
            set
            {
                if (_profilePicturePath != value)
                {
                    _profilePicturePath = value;
                    OnPropertyChanged();
                    OnPropertyChanged(nameof(ProfileImageSource));
                }
            }
        }

        // ==============================================================
        // EL ESCUDO: Evitamos que el JSON intente leer elementos de diseño
        // ==============================================================

        [JsonIgnore]
        public Brush DefaultStarForeground => IsDefault
            ? new SolidColorBrush(Windows.UI.Color.FromArgb(255, 255, 215, 0))
            : (Brush)Application.Current.Resources["TextFillColorSecondaryBrush"];

        [JsonIgnore]
        public Symbol FavoriteSymbol => IsDefault ? Symbol.SolidStar : Symbol.OutlineStar;

        [JsonIgnore]
        public ImageSource? ProfileImageSource
        {
            get
            {
                if (string.IsNullOrWhiteSpace(ProfilePicturePath)) return null;
                try { return new BitmapImage(new Uri(ProfilePicturePath)); }
                catch { return null; }
            }
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        }
    }
}