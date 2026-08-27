using System.Text.Json;
using PasswordDetective.OfficialArchiveSecurity;
using PasswordDetective.Pdpp;

await new OfficialArchiveSecurityPlugin().RunAsync();

internal sealed class OfficialArchiveSecurityPlugin : PdppPlugin
{
    public OfficialArchiveSecurityPlugin() : base(
        "com.passworddetective.official-archive-security",
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
            throw new InvalidOperationException("未知归档安全检查命令。");
        }

        var selected = PluginSelectedFile.FromJson(input.GetProperty("archive"));
        var digest = await host.DigestFileAsync(selected.FileRef, "sha256", cancellationToken);
        if (selected.Length > ArchiveSecurityAnalyzer.MaximumReadableArchiveBytes)
        {
            return ArchiveSecurityAnalyzer.CreateSizeFailure(selected, digest.Digest);
        }

        var bytes = await host.ReadFileToEndAsync(
            selected,
            ArchiveSecurityAnalyzer.MaximumReadableArchiveBytes,
            cancellationToken);
        return ArchiveSecurityAnalyzer.Inspect(selected, bytes, digest.Digest);
    }
}
