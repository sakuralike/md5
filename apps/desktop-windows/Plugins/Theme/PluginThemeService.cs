using System.IO;
using System.Text.Json;
using System.Windows.Media.Imaging;

namespace PasswordDetective.Desktop.Plugins.Theme;

public sealed record PluginThemeSettings(
    string Preset,
    string? BackgroundFileName,
    double BackgroundOpacity);

public interface IPluginThemeService
{
    string ImportBackground(string pluginId, string sourcePath);
    Task<JsonElement> ApplyAsync(string pluginId, JsonElement parameters, string? installedDirectory = null, CancellationToken cancellationToken = default);
    Task ApplyPersistedAsync(CancellationToken cancellationToken = default);
}

public sealed class PluginThemeService : IPluginThemeService
{
    public const long MaximumBackgroundBytes = 10 * 1024 * 1024;

    private static readonly IReadOnlySet<string> Presets = new HashSet<string>(
        ["light", "dark", "forest", "contrast", "ocean", "rose", "amber", "slate"],
        StringComparer.Ordinal);

    private readonly string _backgroundDirectory;
    private readonly string _settingsPath;
    private readonly Func<PluginThemeSettings, CancellationToken, Task> _apply;
    private readonly Dictionary<string, (string PluginId, string FileName)> _imports =
        new(StringComparer.Ordinal);

    public PluginThemeService(
        string rootDirectory,
        Func<PluginThemeSettings, CancellationToken, Task> apply)
    {
        _backgroundDirectory = Path.Combine(rootDirectory, "theme-backgrounds");
        _settingsPath = Path.Combine(rootDirectory, "theme-settings.json");
        _apply = apply;
    }

    public string ImportBackground(string pluginId, string sourcePath)
    {
        var source = new FileInfo(sourcePath);
        if (!source.Exists || source.Length is < 1 or > MaximumBackgroundBytes)
        {
            throw new InvalidOperationException("背景图片不存在或超过 10 MB 限制。");
        }

        var extension = Path.GetExtension(source.Name).ToLowerInvariant();
        if (extension is not (".png" or ".jpg" or ".jpeg"))
        {
            throw new InvalidOperationException("背景图片仅支持 PNG、JPG 或 JPEG 格式。");
        }

        try
        {
            using var stream = source.OpenRead();
            var decoder = BitmapDecoder.Create(
                stream,
                BitmapCreateOptions.PreservePixelFormat,
                BitmapCacheOption.OnLoad);
            if (decoder.Frames.Count != 1 || decoder.Frames[0].PixelWidth < 1 || decoder.Frames[0].PixelHeight < 1)
            {
                throw new InvalidOperationException("背景图片尺寸无效。");
            }
        }
        catch (NotSupportedException exception)
        {
            throw new InvalidOperationException("背景图片格式无效。", exception);
        }

        Directory.CreateDirectory(_backgroundDirectory);
        var reference = Guid.NewGuid().ToString("N");
        var fileName = $"{reference}{extension}";
        File.Copy(source.FullName, Path.Combine(_backgroundDirectory, fileName), overwrite: false);
        _imports[reference] = (pluginId, fileName);
        return reference;
    }

    public async Task<JsonElement> ApplyAsync(
        string pluginId,
        JsonElement parameters,
        string? installedDirectory = null,
        CancellationToken cancellationToken = default)
    {
        if (!parameters.TryGetProperty("preset", out var presetElement)
            || presetElement.ValueKind != JsonValueKind.String
            || !Presets.Contains(presetElement.GetString() ?? string.Empty))
        {
            throw new InvalidOperationException("主题预设无效。");
        }

        var opacity = parameters.TryGetProperty("background_opacity", out var opacityElement)
            && opacityElement.ValueKind == JsonValueKind.Number
            ? opacityElement.GetDouble()
            : 1d;
        if (opacity is < 0.1d or > 1d)
        {
            throw new InvalidOperationException("背景透明度必须在 0.1 到 1 之间。");
        }

        string? backgroundFileName = null;
        if (ReadBoolean(parameters, "use_default_background") && !string.IsNullOrWhiteSpace(installedDirectory))
        {
            var bundled = Path.Combine(installedDirectory, "assets", "default-background.jpg");
            if (File.Exists(bundled))
            {
                backgroundFileName = ImportBackground(pluginId, bundled);
            }
        }
        if (!ReadBoolean(parameters, "clear_background") && backgroundFileName is null)
        {
            if (parameters.TryGetProperty("background_ref", out var reference))
            {
                if (reference.ValueKind == JsonValueKind.String
                    && _imports.TryGetValue(reference.GetString() ?? string.Empty, out var imported)
                    && string.Equals(imported.PluginId, pluginId, StringComparison.Ordinal))
                {
                    backgroundFileName = imported.FileName;
                }
            }
            else if (File.Exists(_settingsPath))
            {
                backgroundFileName = (await ReadSettingsAsync(cancellationToken)).BackgroundFileName;
            }
        }

        var settings = new PluginThemeSettings(presetElement.GetString()!, backgroundFileName, opacity);
        await _apply(settings, cancellationToken);
        await SaveSettingsAsync(settings, cancellationToken);
        return JsonSerializer.SerializeToElement(new
        {
            applied = true,
            preset = settings.Preset,
            has_background = settings.BackgroundFileName is not null,
            background_opacity = settings.BackgroundOpacity,
        });
    }

    public async Task ApplyPersistedAsync(CancellationToken cancellationToken = default)
    {
        if (File.Exists(_settingsPath))
        {
            await _apply(await ReadSettingsAsync(cancellationToken), cancellationToken);
        }
    }

    private async Task<PluginThemeSettings> ReadSettingsAsync(CancellationToken cancellationToken)
    {
        await using var stream = File.OpenRead(_settingsPath);
        return await JsonSerializer.DeserializeAsync<PluginThemeSettings>(stream, cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("主题设置文件无效。");
    }

    private async Task SaveSettingsAsync(PluginThemeSettings settings, CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_settingsPath)!);
        var temporary = $"{_settingsPath}.{Guid.NewGuid():N}.tmp";
        await using (var stream = File.Create(temporary))
        {
            await JsonSerializer.SerializeAsync(stream, settings, cancellationToken: cancellationToken);
        }

        File.Move(temporary, _settingsPath, overwrite: true);
    }

    private static bool ReadBoolean(JsonElement parameters, string name) =>
        parameters.TryGetProperty(name, out var value)
        && value.ValueKind == JsonValueKind.True;
}
