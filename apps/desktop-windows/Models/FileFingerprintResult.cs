namespace PasswordDetective.Desktop.Models;

public sealed record FileFingerprintResult(
    string FileName,
    long FileSize,
    string Sha256,
    string Md5,
    DateTimeOffset CalculatedAt);
