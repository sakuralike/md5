namespace PasswordDetective.Desktop.Models;

public sealed record ArchiveVerificationLimits
{
    public long MaxArchiveBytes { get; init; } = 8L * 1024 * 1024 * 1024;
    public int MaxEntries { get; init; } = 10_000;
    public long MaxExpandedBytes { get; init; } = 32L * 1024 * 1024 * 1024;
    public double MaxCompressionRatio { get; init; } = 1_000;
    public long RatioCheckMinimumBytes { get; init; } = 1024 * 1024;
    public long MaxSampleBytes { get; init; } = 1024 * 1024;
    public TimeSpan VerificationTimeout { get; init; } = TimeSpan.FromSeconds(30);

    public void Validate()
    {
        if (MaxArchiveBytes <= 0
            || MaxEntries <= 0
            || MaxExpandedBytes <= 0
            || MaxCompressionRatio <= 0
            || RatioCheckMinimumBytes <= 0
            || MaxSampleBytes <= 0
            || VerificationTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(
                nameof(ArchiveVerificationLimits),
                "压缩包验证限制必须全部大于零。");
        }
    }
}
