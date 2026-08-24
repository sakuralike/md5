using System.Text.Json;
using System.IO;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.ViewModels;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginCommandFormTests : IDisposable
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-command-form",
        Guid.NewGuid().ToString("N"));

    public PluginCommandFormTests() => Directory.CreateDirectory(_directory);

    [Fact]
    public void HostBuildsSupportedControlsAndStructuredInputFromSchema()
    {
        var schemaPath = Path.Combine(_directory, "input.schema.json");
        File.WriteAllText(
            schemaPath,
            """
            {
              "type": "object",
              "required": ["message", "count"],
              "properties": {
                "message": {"type": "string", "title": "消息"},
                "count": {"type": "integer", "title": "次数"},
                "ratio": {"type": "number", "title": "比例"},
                "enabled": {"type": "boolean", "title": "启用"},
                "mode": {"type": "string", "title": "模式", "enum": ["safe", "strict"]},
                "file": {"type": "string", "format": "file", "title": "文件"},
                "directory": {"type": "string", "format": "directory", "title": "目录"}
              }
            }
            """);
        var form = PluginCommandForm.Load(
            schemaPath,
            kind => kind == PluginCommandFieldKind.File ? "C:\\synthetic.txt" : "C:\\synthetic");

        form.Fields.Single(field => field.Name == "message").Value = "hello";
        form.Fields.Single(field => field.Name == "count").Value = "3";
        form.Fields.Single(field => field.Name == "ratio").Value = "1.5";
        form.Fields.Single(field => field.Name == "enabled").BooleanValue = true;
        form.Fields.Single(field => field.Name == "file").BrowseCommand.Execute(null);
        form.Fields.Single(field => field.Name == "directory").BrowseCommand.Execute(null);
        var input = form.BuildInput();

        Assert.Equal(7, form.Fields.Count);
        Assert.Equal("hello", input.GetProperty("message").GetString());
        Assert.Equal(3, input.GetProperty("count").GetInt64());
        Assert.Equal(1.5m, input.GetProperty("ratio").GetDecimal());
        Assert.True(input.GetProperty("enabled").GetBoolean());
        Assert.Equal("safe", input.GetProperty("mode").GetString());
        Assert.Equal("C:\\synthetic.txt", input.GetProperty("file").GetString());
    }

    [Fact]
    public void UnsupportedSchemaTypeIsRejectedWithoutLoadingPluginUi()
    {
        var schemaPath = Path.Combine(_directory, "unsupported.schema.json");
        File.WriteAllText(
            schemaPath,
            """{"type":"object","properties":{"payload":{"type":"array"}}}""");

        Assert.Throws<PluginPackageException>(
            () => PluginCommandForm.Load(schemaPath, _ => null));
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }
}
