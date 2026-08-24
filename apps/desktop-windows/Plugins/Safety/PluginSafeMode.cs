using System.Diagnostics;
using System.IO;
using System.Text.Json;
using PasswordDetective.Desktop.Plugins.Storage;

namespace PasswordDetective.Desktop.Plugins.Safety;

public sealed class PluginSafeMode
{
    private readonly PluginStoragePaths _paths;
    private readonly int _processId = Environment.ProcessId;

    public PluginSafeMode(PluginStoragePaths paths) => _paths = paths;

    public bool IsActive { get; private set; }

    public void BeginSession()
    {
        _paths.EnsureDirectories();
        var previous = ReadMarker();
        IsActive = previous is not null && !IsProcessRunning(previous.ProcessId);
        WriteMarker(new SafeModeMarker(_processId, DateTimeOffset.UtcNow));
    }

    public void LeaveSafeModeForCurrentSession() => IsActive = false;

    public void MarkCleanExit()
    {
        var marker = ReadMarker();
        if (marker?.ProcessId == _processId && File.Exists(_paths.SafeModeMarkerPath))
        {
            File.Delete(_paths.SafeModeMarkerPath);
        }
    }

    private SafeModeMarker? ReadMarker()
    {
        if (!File.Exists(_paths.SafeModeMarkerPath))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<SafeModeMarker>(
                File.ReadAllText(_paths.SafeModeMarkerPath));
        }
        catch (Exception exception) when (exception is JsonException or IOException)
        {
            return new SafeModeMarker(-1, DateTimeOffset.MinValue);
        }
    }

    private void WriteMarker(SafeModeMarker marker)
    {
        var temporaryPath = $"{_paths.SafeModeMarkerPath}.{Guid.NewGuid():N}.tmp";
        File.WriteAllText(temporaryPath, JsonSerializer.Serialize(marker));
        if (File.Exists(_paths.SafeModeMarkerPath))
        {
            File.Replace(temporaryPath, _paths.SafeModeMarkerPath, destinationBackupFileName: null);
        }
        else
        {
            File.Move(temporaryPath, _paths.SafeModeMarkerPath);
        }
    }

    private static bool IsProcessRunning(int processId)
    {
        if (processId <= 0)
        {
            return false;
        }

        try
        {
            using var process = Process.GetProcessById(processId);
            return !process.HasExited;
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    private sealed record SafeModeMarker(int ProcessId, DateTimeOffset StartedAt);
}
