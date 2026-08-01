using PasswordDetective.Desktop.Models;

namespace PasswordDetective.Desktop.Services;

public interface IFileFingerprintService
{
    Task<FileFingerprintResult> CalculateAsync(
        string filePath,
        IProgress<double>? progress = null,
        CancellationToken cancellationToken = default);
}
