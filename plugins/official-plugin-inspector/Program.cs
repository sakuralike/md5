using System.Text.Json;
using PasswordDetective.OfficialPluginInspector;
using PasswordDetective.Pdpp;

await new OfficialPluginInspectorPlugin().RunAsync();

internal sealed class OfficialPluginInspectorPlugin : PdppPlugin
{
    public OfficialPluginInspectorPlugin() : base(
        "com.passworddetective.official-plugin-inspector",
        "1.0.0",
        ["ui:command", "file:read:selected"])
    {
    }

    protected override async Task<object> ExecuteAsync(
        string command,
        JsonElement input,
        PdppHostClient host,
        CancellationToken cancellationToken)
    {
        if (command != "inspect")
        {
            throw new InvalidOperationException("未知体检命令。");
        }

        var selected = PluginSelectedFile.FromJson(input.GetProperty("package"));
        var digest = await host.DigestFileAsync(
            selected.FileRef,
            "sha256",
            cancellationToken);
        if (selected.Length > PackageInspector.MaximumReadablePackageBytes)
        {
            return PackageInspector.CreateSizeFailure(selected, digest.Digest);
        }

        var bytes = await host.ReadFileToEndAsync(
            selected,
            PackageInspector.MaximumReadablePackageBytes,
            cancellationToken);
        return PackageInspector.Inspect(selected, bytes, digest.Digest);
    }
}
