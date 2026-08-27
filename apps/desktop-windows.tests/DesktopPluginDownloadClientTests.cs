using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using PasswordDetective.Desktop.Services;

namespace PasswordDetective.Desktop.Tests;

public sealed class DesktopPluginDownloadClientTests : IDisposable
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-plugin-download-tests",
        Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task DownloadClosesDestinationBeforeHashVerification()
    {
        var content = "synthetic plugin package"u8.ToArray();
        using var httpClient = new HttpClient(new ArtifactHandler(content));
        using var client = new DesktopApiClient(httpClient);
        Directory.CreateDirectory(_directory);
        var destination = Path.Combine(_directory, "plugin.pdpkg");

        await client.DownloadPluginArtifactAsync(
            "https://plugins.synthetic.example/download",
            destination,
            Convert.ToHexStringLower(SHA256.HashData(content)),
            content.Length);

        Assert.Equal(content, await File.ReadAllBytesAsync(destination));
        using var exclusive = new FileStream(destination, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
        Assert.Equal(content.Length, exclusive.Length);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory))
        {
            Directory.Delete(_directory, recursive: true);
        }
    }

    private sealed class ArtifactHandler(byte[] content) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(content),
            });
    }
}
