using PasswordDetective.Desktop.Models;

namespace PasswordDetective.Desktop.Services;

public interface IArchiveVerificationService
{
    Task<ArchiveVerificationResult> VerifyAsync(
        string filePath,
        string candidatePassword,
        CancellationToken cancellationToken = default);
}
