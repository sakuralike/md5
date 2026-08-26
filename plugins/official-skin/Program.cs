using System.Text.Json;
using PasswordDetective.Pdpp;

await new OfficialSkinPlugin().RunAsync();

internal sealed class OfficialSkinPlugin : PdppPlugin
{
    public OfficialSkinPlugin() : base(
        "com.passworddetective.official-skin",
        "1.0.0",
        ["ui:command", "ui:theme"])
    {
    }

    protected override async Task<object> ExecuteAsync(
        string command,
        JsonElement input,
        PdppHostClient host,
        CancellationToken cancellationToken)
    {
        if (command != "apply")
        {
            throw new InvalidOperationException("未知皮肤命令。");
        }

        var preset = input.GetProperty("preset").GetString() ?? "light";
        var clearBackground = input.TryGetProperty("clear_background", out var clearElement)
            && clearElement.ValueKind == JsonValueKind.True;
        var backgroundReference = input.TryGetProperty("background", out var background)
            && background.ValueKind == JsonValueKind.Object
            && background.TryGetProperty("background_ref", out var reference)
            ? reference.GetString()
            : null;
        var result = await host.ApplyThemeAsync(
            preset,
            backgroundReference,
            1d,
            clearBackground,
            cancellationToken);
        return new
        {
            applied = result.GetProperty("applied").GetBoolean(),
            preset,
            has_background = result.GetProperty("has_background").GetBoolean(),
        };
    }
}
