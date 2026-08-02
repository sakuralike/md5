namespace PasswordDetective.Desktop.Models;

public sealed record DesktopRecoveryAdvice(
    string Message,
    bool CanRegenerateInstallation,
    bool UpgradeRequired);
