using PasswordDetective.Desktop.Protocol;

namespace PasswordDetective.Desktop.Services;

public interface IDesktopApiClient
{
    Task<bool> TestConnectivityAsync(
        string serverBaseUrl,
        CancellationToken cancellationToken = default);

    Task<DesktopAnnouncementListResponse> GetAnnouncementsAsync(
        string serverBaseUrl,
        CancellationToken cancellationToken = default);

    Task<TrustProfileResponse> GetTrustProfileAsync(
        string serverBaseUrl,
        string accessToken,
        CancellationToken cancellationToken = default);

    Task<DesktopUpdateCheckResponse> CheckForUpdateAsync(
        string serverBaseUrl,
        string currentVersion,
        string channel,
        string platform,
        string architecture,
        CancellationToken cancellationToken = default);

    Task<TokenResponse> LoginAsync(
        string serverBaseUrl,
        LoginRequest request,
        CancellationToken cancellationToken = default);

    Task<TokenResponse> RefreshAsync(
        string serverBaseUrl,
        RefreshRequest request,
        CancellationToken cancellationToken = default);

    Task<InstallationResponse> RegisterInstallationAsync(
        string serverBaseUrl,
        string accessToken,
        InstallationRegistrationRequest request,
        CancellationToken cancellationToken = default);

    Task<ChallengeResponse> CreateChallengeAsync(
        string serverBaseUrl,
        string accessToken,
        ChallengeRequest request,
        CancellationToken cancellationToken = default);

    Task<ReceiptResponse> SubmitReceiptAsync(
        string serverBaseUrl,
        string accessToken,
        ReceiptRequest request,
        CancellationToken cancellationToken = default);
}
