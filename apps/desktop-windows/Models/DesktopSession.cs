namespace PasswordDetective.Desktop.Models;

public sealed record DesktopSession(
    string ServerBaseUrl,
    string AccessToken,
    string RefreshToken,
    string AccountId,
    string Username,
    DateTimeOffset ExpiresAt);
