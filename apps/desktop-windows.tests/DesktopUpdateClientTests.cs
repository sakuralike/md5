using System.Net;
using System.Net.Http;
using System.Text;
using PasswordDetective.Desktop.Services;

namespace PasswordDetective.Desktop.Tests;

public sealed class DesktopUpdateClientTests
{
    [Fact]
    public async Task UpdateCheckUsesPublicBackendChannelAndParsesManifest()
    {
        var handler = new RecordingHandler(
            """
            {
              "update_available": true,
              "mandatory": false,
              "current_version": "0.1.0",
              "latest_version": "0.2.0",
              "minimum_supported_version": "0.1.0",
              "channel": "stable",
              "platform": "windows",
              "architecture": "x64",
              "release_id": "11111111-1111-1111-1111-111111111111",
              "release_notes": "synthetic release notes",
              "published_at": "2026-08-02T00:00:00Z",
              "download_url": "https://updates.synthetic.example/api/v1/desktop/updates/111/download",
              "artifact_filename": "password-detective-0.2.0-x64.msix",
              "artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              "artifact_size_bytes": 4096,
              "artifact_integrity": "sha256-verified",
              "distribution_authorized": true
            }
            """);
        using var httpClient = new HttpClient(handler);
        using var client = new DesktopApiClient(httpClient);

        var update = await client.CheckForUpdateAsync(
            "https://api.synthetic.example/api/v1/",
            "0.1.0",
            "stable",
            "windows",
            "x64");

        Assert.True(update.UpdateAvailable);
        Assert.Equal("0.2.0", update.LatestVersion);
        Assert.Equal("sha256-verified", update.ArtifactIntegrity);
        Assert.True(update.DistributionAuthorized);
        Assert.NotNull(handler.LastRequestUri);
        Assert.Equal("/api/v1/desktop/updates/check", handler.LastRequestUri!.AbsolutePath);
        Assert.Contains("current_version=0.1.0", handler.LastRequestUri.Query);
        Assert.Contains("architecture=x64", handler.LastRequestUri.Query);
    }

    private sealed class RecordingHandler(string responseBody) : HttpMessageHandler
    {
        public Uri? LastRequestUri { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            LastRequestUri = request.RequestUri;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(responseBody, Encoding.UTF8, "application/json"),
            });
        }
    }
}
