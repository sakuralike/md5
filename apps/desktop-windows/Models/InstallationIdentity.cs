namespace PasswordDetective.Desktop.Models;

public sealed record InstallationIdentity(
    Guid InstallationId,
    string PublicKey,
    string PublicKeyFingerprint,
    string KeyAlgorithm,
    DateTimeOffset CreatedAt);
