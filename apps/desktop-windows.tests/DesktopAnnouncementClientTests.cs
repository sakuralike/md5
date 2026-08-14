using System.Net;
using System.Net.Http;
using System.Text;
using PasswordDetective.Desktop.Services;
using PasswordDetective.Desktop.ViewModels;

namespace PasswordDetective.Desktop.Tests;

public sealed class DesktopAnnouncementClientTests
{
    [Theory]
    [InlineData("http://111.229.195.138:5173", "/api/v1/desktop/announcements")]
    [InlineData("http://111.229.195.138:5173/api/v1/", "/api/v1/desktop/announcements")]
    [InlineData("https://synthetic.example.com/proxy", "/proxy/api/v1/desktop/announcements")]
    public async Task AnnouncementRequestNormalizesApiBaseAndBypassesCache(
        string serverBaseUrl,
        string expectedPath)
    {
        var handler = new RecordingHandler("{\"items\":[]}");
        using var httpClient = new HttpClient(handler);
        using var client = new DesktopApiClient(httpClient);

        var response = await client.GetAnnouncementsAsync(serverBaseUrl);

        Assert.Empty(response.Items);
        Assert.NotNull(handler.LastRequest);
        Assert.Equal(expectedPath, handler.LastRequest!.RequestUri!.AbsolutePath);
        Assert.Contains("limit=10", handler.LastRequest.RequestUri.Query);
        Assert.Contains("refresh=", handler.LastRequest.RequestUri.Query);
        Assert.True(handler.LastRequest.Headers.CacheControl?.NoCache);
        Assert.True(handler.LastRequest.Headers.CacheControl?.NoStore);
    }

    [Fact]
    public void DefaultBackendUsesTheReachableStagingProxy()
    {
        Assert.Equal(
            "http://111.229.195.138:5173/api/v1/",
            MainWindowViewModel.DefaultServerBaseUrl);
    }

    private sealed class RecordingHandler(string responseBody) : HttpMessageHandler
    {
        public HttpRequestMessage? LastRequest { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            LastRequest = request;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(responseBody, Encoding.UTF8, "application/json"),
            });
        }
    }
}
