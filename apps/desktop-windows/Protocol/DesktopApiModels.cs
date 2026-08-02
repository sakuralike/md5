using System.Text.Json;

namespace PasswordDetective.Desktop.Protocol;

public sealed record LoginRequest(string Login, string Password, string? TotpCode);

public sealed record ApiUser(string Id, string Username);

public sealed record TokenResponse(
    string AccessToken,
    string RefreshToken,
    string TokenType,
    int ExpiresIn,
    bool MfaVerified,
    ApiUser User);

public sealed record RefreshRequest(string RefreshToken);

public sealed record DesktopUpdateCheckResponse(
    bool UpdateAvailable,
    bool Mandatory,
    string CurrentVersion,
    string? LatestVersion,
    string? MinimumSupportedVersion,
    string Channel,
    string Platform,
    string Architecture,
    string? ReleaseId,
    string ReleaseNotes,
    DateTimeOffset? PublishedAt,
    string? DownloadUrl,
    string? ArtifactFilename,
    string? ArtifactSha256,
    long? ArtifactSizeBytes,
    string? CodeSignatureStatus,
    string? SignerSubject,
    string? SignerThumbprint);

public sealed record InstallationRegistrationRequest(
    Guid InstallationId,
    string PublicKey,
    string KeyAlgorithm,
    string ClientVersion);

public sealed record InstallationResponse(
    string InstallationId,
    string Status,
    string PublicKeyFingerprint,
    string ClientVersion,
    int ReceiptCount);

public sealed record ChallengeRequest(
    Guid InstallationId,
    string CandidateId,
    string FingerprintAlgorithm,
    string FingerprintDigest,
    string ClientVersion);

public sealed record ChallengeResponse(
    string ChallengeId,
    string ChallengeNonce,
    string InstallationId,
    string AccountId,
    string CandidateId,
    string FingerprintAlgorithm,
    string FingerprintDigest,
    string ClientVersion,
    string CanonicalPayloadVersion,
    DateTimeOffset ExpiresAt);

public sealed record ReceiptRequest(
    string ChallengeId,
    string ChallengeNonce,
    Guid InstallationId,
    string AccountId,
    string CandidateId,
    string FingerprintAlgorithm,
    string FingerprintDigest,
    string CandidateDigest,
    string Outcome,
    string ArchiveFormat,
    string ClientVersion,
    DateTimeOffset VerifiedAt,
    string Signature);

public sealed record ReceiptResponse(
    string ReceiptId,
    string? EvidenceEventId,
    string CandidateId,
    string Outcome,
    string CandidateStatus,
    DateTimeOffset AcceptedAt);

public sealed record ApiErrorBody(
    string Code,
    string Message,
    Dictionary<string, JsonElement>? Details);
