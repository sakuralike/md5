using System.IO;
using System.Text.Json;
using PasswordDetective.Desktop.Plugins.Theme;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginThemeServiceTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "password-detective-theme-tests", Guid.NewGuid().ToString("N"));

    public PluginThemeServiceTests() => Directory.CreateDirectory(_directory);

    [Fact]
    public async Task ImportsValidatedImageAndOnlyItsOwnerCanApplyReference()
    {
        var source = Path.Combine(_directory, "wallpaper.png");
        await File.WriteAllBytesAsync(source, Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLh6AAAAABJRU5ErkJggg=="));
        PluginThemeSettings? applied = null;
        var service = new PluginThemeService(_directory, (settings, _) =>
        {
            applied = settings;
            return Task.CompletedTask;
        });

        var reference = service.ImportBackground("official.theme", source);
        var result = await service.ApplyAsync("official.theme", JsonSerializer.SerializeToElement(new
        {
            preset = "forest",
            background_ref = reference,
            background_opacity = 0.6,
        }));

        Assert.True(result.GetProperty("has_background").GetBoolean());
        Assert.Equal("forest", applied?.Preset);
        Assert.NotNull(applied?.BackgroundFileName);
        Assert.Equal(0.6, applied?.BackgroundOpacity);
        var unauthorized = await service.ApplyAsync("other.plugin", JsonSerializer.SerializeToElement(new
        {
            preset = "dark",
            background_ref = reference,
        }));
        Assert.False(unauthorized.GetProperty("has_background").GetBoolean());
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }
}
