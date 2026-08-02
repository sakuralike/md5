using System.Globalization;
using System.Text;

namespace PasswordDetective.Desktop.Protocol;

public sealed record DesktopReceiptPayload(
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
    DateTimeOffset VerifiedAt);

public static class DesktopReceiptCanonicalizer
{
    public const string Version = "desktop-receipt-v1";

    public static byte[] Build(DesktopReceiptPayload payload)
    {
        ArgumentNullException.ThrowIfNull(payload);
        var timestamp = payload.VerifiedAt.ToUniversalTime().ToString(
            "yyyy-MM-dd'T'HH:mm:ss.fff'Z'",
            CultureInfo.InvariantCulture);
        var lines = new[]
        {
            $"version={Version}",
            $"challenge_id={payload.ChallengeId}",
            $"challenge_nonce={payload.ChallengeNonce}",
            $"installation_id={payload.InstallationId:D}",
            $"account_id={payload.AccountId}",
            $"candidate_id={payload.CandidateId}",
            $"fingerprint_algorithm={payload.FingerprintAlgorithm}",
            $"fingerprint_digest={payload.FingerprintDigest.ToLowerInvariant()}",
            $"candidate_digest={payload.CandidateDigest.ToLowerInvariant()}",
            $"outcome={payload.Outcome}",
            $"archive_format={payload.ArchiveFormat}",
            $"client_version={payload.ClientVersion}",
            $"verified_at={timestamp}",
        };
        return Encoding.UTF8.GetBytes(string.Join('\n', lines) + "\n");
    }
}
