namespace PasswordDetective.Desktop.Models;

public sealed record ArchiveVerificationResult(
    bool Success,
    string ArchiveFormat,
    int EntryCount,
    long TotalUncompressedBytes,
    long BytesSampled,
    string Message,
    DateTimeOffset CompletedAt);
