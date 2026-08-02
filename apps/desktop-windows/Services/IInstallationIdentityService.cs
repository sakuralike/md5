using PasswordDetective.Desktop.Models;

namespace PasswordDetective.Desktop.Services;

public interface IInstallationIdentityService
{
    Task<InstallationIdentity> GetOrCreateAsync(CancellationToken cancellationToken = default);

    Task<string> SignAsync(
        ReadOnlyMemory<byte> canonicalPayload,
        CancellationToken cancellationToken = default);
}
