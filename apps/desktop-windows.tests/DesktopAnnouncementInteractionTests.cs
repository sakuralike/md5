using PasswordDetective.Desktop.Models;
using PasswordDetective.Desktop.Protocol;
using PasswordDetective.Desktop.Services;
using PasswordDetective.Desktop.ViewModels;

namespace PasswordDetective.Desktop.Tests;

public sealed class DesktopAnnouncementInteractionTests
{
    [Fact]
    public void AnnouncementTextRefreshesAndConfiguredImageLinkOpens()
    {
        var api = new AnnouncementApiClient();
        var launcher = new RecordingExternalUriLauncher();
        var viewModel = new MainWindowViewModel(
            new UnusedFingerprintService(),
            new UnusedArchiveVerificationService(),
            new SyntheticIdentityService(),
            api,
            new EmptySessionStore(),
            launcher);

        Assert.Equal(1, api.AnnouncementRequestCount);
        Assert.Equal("合成公告", viewModel.CurrentAnnouncementTitle);

        viewModel.RefreshAnnouncementsCommand.Execute(null);

        Assert.Equal(2, api.AnnouncementRequestCount);
        Assert.Equal("共 1 条公告", viewModel.AnnouncementStatus);
        Assert.True(viewModel.OpenAnnouncementActionCommand.CanExecute(null));

        viewModel.OpenAnnouncementActionCommand.Execute(null);

        Assert.Equal("https://synthetic.example/notice", launcher.LastUri?.AbsoluteUri);
        Assert.Equal("已在系统浏览器中打开公告链接。", viewModel.Status);
    }

    private sealed class AnnouncementApiClient : IDesktopApiClient
    {
        public int AnnouncementRequestCount { get; private set; }

        public Task<bool> TestConnectivityAsync(string serverBaseUrl, CancellationToken cancellationToken = default) =>
            Task.FromResult(true);

        public Task<DesktopAnnouncementListResponse> GetAnnouncementsAsync(
            string serverBaseUrl,
            CancellationToken cancellationToken = default)
        {
            AnnouncementRequestCount++;
            var item = new DesktopAnnouncement(
                "11111111-1111-1111-1111-111111111111",
                "合成公告",
                "点击文字区刷新，点击图片打开链接。",
                "text",
                ["https://synthetic.example/notice.png"],
                null,
                "https://synthetic.example/notice",
                10,
                null,
                null,
                "published",
                1,
                DateTimeOffset.Parse("2026-08-14T00:00:00Z"));
            return Task.FromResult(new DesktopAnnouncementListResponse([item]));
        }

        public Task<DesktopUpdateCheckResponse> CheckForUpdateAsync(
            string serverBaseUrl,
            string currentVersion,
            string channel,
            string platform,
            string architecture,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new DesktopUpdateCheckResponse(
                false,
                false,
                currentVersion,
                currentVersion,
                currentVersion,
                channel,
                platform,
                architecture,
                null,
                string.Empty,
                null,
                null,
                null,
                null,
                null,
                null,
                true));

        public Task<TrustProfileResponse> GetTrustProfileAsync(string serverBaseUrl, string accessToken, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<TokenResponse> LoginAsync(string serverBaseUrl, LoginRequest request, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<TokenResponse> RefreshAsync(string serverBaseUrl, RefreshRequest request, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<InstallationResponse> RegisterInstallationAsync(string serverBaseUrl, string accessToken, InstallationRegistrationRequest request, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<ChallengeResponse> CreateChallengeAsync(string serverBaseUrl, string accessToken, ChallengeRequest request, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<ReceiptResponse> SubmitReceiptAsync(string serverBaseUrl, string accessToken, ReceiptRequest request, CancellationToken cancellationToken = default) => throw new NotSupportedException();
    }

    private sealed class SyntheticIdentityService : IInstallationIdentityService
    {
        private static readonly InstallationIdentity Identity = new(
            Guid.Parse("22222222-2222-2222-2222-222222222222"),
            "synthetic-public-key",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "Ed25519",
            DateTimeOffset.Parse("2026-08-14T00:00:00Z"));

        public Task<InstallationIdentity> GetOrCreateAsync(CancellationToken cancellationToken = default) => Task.FromResult(Identity);
        public Task<InstallationIdentity> RegenerateAsync(CancellationToken cancellationToken = default) => Task.FromResult(Identity);
        public Task<string> SignAsync(ReadOnlyMemory<byte> canonicalPayload, CancellationToken cancellationToken = default) => Task.FromResult("synthetic-signature");
    }

    private sealed class EmptySessionStore : IProtectedSessionStore
    {
        public Task<DesktopSession?> LoadAsync(CancellationToken cancellationToken = default) => Task.FromResult<DesktopSession?>(null);
        public Task SaveAsync(DesktopSession session, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public void Clear() { }
    }

    private sealed class RecordingExternalUriLauncher : IExternalUriLauncher
    {
        public Uri? LastUri { get; private set; }
        public void Open(Uri uri) => LastUri = uri;
    }

    private sealed class UnusedFingerprintService : IFileFingerprintService
    {
        public Task<FileFingerprintResult> CalculateAsync(string filePath, IProgress<double>? progress = null, CancellationToken cancellationToken = default) => throw new NotSupportedException();
    }

    private sealed class UnusedArchiveVerificationService : IArchiveVerificationService
    {
        public Task<ArchiveVerificationResult> VerifyAsync(string filePath, string candidatePassword, CancellationToken cancellationToken = default) => throw new NotSupportedException();
    }
}
