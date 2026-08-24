namespace PasswordDetective.Desktop.Plugins.Packages;

public sealed class PluginPackageLimits
{
    public const long DefaultMaximumPackageBytes = 512L * 1024 * 1024;
    public const long DefaultMaximumExpandedBytes = 1024L * 1024 * 1024;
    public const long DefaultMaximumSingleFileBytes = 256L * 1024 * 1024;
    public const int DefaultMaximumEntries = 2048;
    public const double DefaultMaximumCompressionRatio = 100;

    public long MaximumPackageBytes { get; init; } = DefaultMaximumPackageBytes;
    public long MaximumExpandedBytes { get; init; } = DefaultMaximumExpandedBytes;
    public long MaximumSingleFileBytes { get; init; } = DefaultMaximumSingleFileBytes;
    public int MaximumEntries { get; init; } = DefaultMaximumEntries;
    public double MaximumCompressionRatio { get; init; } = DefaultMaximumCompressionRatio;

    internal void Validate()
    {
        if (MaximumPackageBytes < 1024 * 1024
            || MaximumExpandedBytes < MaximumPackageBytes
            || MaximumSingleFileBytes < 1024 * 1024
            || MaximumSingleFileBytes > MaximumExpandedBytes
            || MaximumEntries is < 1 or > 10000
            || MaximumCompressionRatio is < 1 or > 1000)
        {
            throw new ArgumentException("Plugin package limits are invalid.");
        }
    }
}
