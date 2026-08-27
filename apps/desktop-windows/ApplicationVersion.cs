using System.Reflection;

namespace PasswordDetective.Desktop;

public static class ApplicationVersion
{
    public static string Current { get; } = Format(
        Assembly.GetExecutingAssembly().GetName().Version);
    public static string WindowTitle => $"密码侦探社-桌面端 v{Current}";

    private static string Format(Version? version) => version is null
        ? "1.0.0"
        : $"{version.Major}.{version.Minor}.{version.Build}";
}
