using System.Text.Json;
using PasswordDetective.Desktop.Plugins;
using PasswordDetective.Desktop.Plugins.Protocol;

if (args.Length != 1 || !File.Exists(args[0]))
{
    Console.Error.WriteLine("Usage: PdppConformance <matrix.json>");
    return 2;
}

var matrix = JsonSerializer.Deserialize<List<PluginEntry>>(
    await File.ReadAllTextAsync(args[0]),
    PdppProtocol.SerializerOptions) ?? [];
var expectedLanguages = new HashSet<string>(["csharp", "go", "rust", "python"], StringComparer.Ordinal);
if (matrix.Count != expectedLanguages.Count
    || !expectedLanguages.SetEquals(matrix.Select(entry => entry.Language)))
{
    Console.Error.WriteLine("The PDPP conformance matrix must contain C#, Go, Rust, and Python exactly once.");
    return 3;
}

foreach (var entry in matrix)
{
    if (!Path.IsPathFullyQualified(entry.ExecutablePath) || !File.Exists(entry.ExecutablePath))
    {
        Console.Error.WriteLine($"Missing {entry.Language} plugin executable: {entry.ExecutablePath}");
        return 4;
    }

    var workingDirectory = Path.Combine(
        Path.GetDirectoryName(args[0])!,
        "runs",
        entry.Language);
    Directory.CreateDirectory(workingDirectory);
    try
    {
        var options = new PluginProcessStartOptions
        {
            PluginId = entry.PluginId,
            ExecutablePath = entry.ExecutablePath,
            WorkingDirectory = workingDirectory,
            MemoryLimitBytes = 256L * 1024 * 1024,
            ActiveProcessLimit = 2,
            DeleteAppContainerProfileOnDispose = true,
        };
        await using var host = await PluginProcessHost.StartAsync(options);
        var initialized = await host.InitializeAsync(
            "0.1.0",
            ["command.echo"],
            TimeSpan.FromSeconds(15));
        var health = await host.InvokeAsync<object, PdppHealthResult>(
            PdppProtocol.HealthCheckMethod,
            new { },
            TimeSpan.FromSeconds(10));
        var input = $"synthetic-pdpp-{entry.Language}";
        var echo = await host.InvokeAsync<PdppCommandParams, EchoResult>(
            PdppProtocol.ExecuteCommandMethod,
            new PdppCommandParams("echo", JsonSerializer.SerializeToElement(input)),
            TimeSpan.FromSeconds(10));

        if (!host.IsAppContainer
            || initialized.PluginId != entry.PluginId
            || initialized.ProtocolVersion != PdppProtocol.ProtocolVersion
            || health.Status != "healthy"
            || echo.Output != input
            || echo.Language != entry.Language)
        {
            Console.Error.WriteLine($"{entry.Language} failed the PDPP v1 contract.");
            return 5;
        }

        Console.WriteLine($"{entry.Language}: PDPP v1 passed in AppContainer (PID {host.ProcessId}).");
    }
    catch (PdppProcessExitedException exception)
    {
        Console.Error.WriteLine(
            $"{entry.Language} exited with code {exception.ExitCode}: {exception.StandardError}");
        return 6;
    }
    finally
    {
        Directory.Delete(workingDirectory, recursive: true);
    }
}

return 0;

internal sealed record PluginEntry(string PluginId, string Language, string ExecutablePath);
internal sealed record EchoResult(string Output, string Language);
