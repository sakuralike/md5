using System.Text;

namespace PasswordDetective.Desktop.Services;

public static class PluginCanaryCanonicalizer
{
    public static byte[] BuildTicketRequest(
        string versionId,
        string architecture,
        Guid installationId) => Build(
        ("version", "desktop-plugin-canary-ticket-v1"),
        ("version_id", versionId),
        ("architecture", architecture),
        ("installation_id", installationId.ToString("D")));

    public static byte[] BuildDownload(string downloadUrl, Guid installationId)
    {
        var token = new Uri(downloadUrl, UriKind.Absolute).Segments.Last().Trim('/');
        return Build(
            ("version", "desktop-plugin-canary-download-v1"),
            ("token", Uri.UnescapeDataString(token)),
            ("installation_id", installationId.ToString("D")));
    }

    private static byte[] Build(params (string Key, string Value)[] values) =>
        Encoding.UTF8.GetBytes(
            string.Join('\n', values.Select(item => $"{item.Key}={item.Value}")) + "\n");
}
