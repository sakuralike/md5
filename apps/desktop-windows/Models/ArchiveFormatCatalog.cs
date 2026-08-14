using System.IO;

namespace PasswordDetective.Desktop.Models;

public static class ArchiveFormatCatalog
{
    public const string Unknown = "unknown";

    public const string SupportedExtensions =
        "*.zip;*.7z;*.rar;*.tar;*.gz;*.tgz;*.tar.gz;*.bz;*.bz2;*.tar.bz;*.tbz;*.tbz2;*.tar.bz2";

    public const string SupportedFormatsDescription =
        "ZIP、7z、RAR、TAR、GZ、TGZ、BZ/BZ2";

    public static bool IsSupportedPath(string filePath)
    {
        if (string.IsNullOrWhiteSpace(filePath))
        {
            return false;
        }

        var fileName = Path.GetFileName(filePath).ToLowerInvariant();
        return fileName.EndsWith(".zip", StringComparison.Ordinal)
            || fileName.EndsWith(".7z", StringComparison.Ordinal)
            || fileName.EndsWith(".rar", StringComparison.Ordinal)
            || fileName.EndsWith(".tar", StringComparison.Ordinal)
            || fileName.EndsWith(".gz", StringComparison.Ordinal)
            || fileName.EndsWith(".tgz", StringComparison.Ordinal)
            || fileName.EndsWith(".bz", StringComparison.Ordinal)
            || fileName.EndsWith(".bz2", StringComparison.Ordinal)
            || fileName.EndsWith(".tbz", StringComparison.Ordinal)
            || fileName.EndsWith(".tbz2", StringComparison.Ordinal);
    }

    public static bool IsGZipPath(string filePath)
    {
        var fileName = Path.GetFileName(filePath).ToLowerInvariant();
        return fileName.EndsWith(".gz", StringComparison.Ordinal)
            || fileName.EndsWith(".tgz", StringComparison.Ordinal);
    }

    public static bool IsBZip2Path(string filePath)
    {
        var fileName = Path.GetFileName(filePath).ToLowerInvariant();
        return fileName.EndsWith(".bz", StringComparison.Ordinal)
            || fileName.EndsWith(".bz2", StringComparison.Ordinal)
            || fileName.EndsWith(".tbz", StringComparison.Ordinal)
            || fileName.EndsWith(".tbz2", StringComparison.Ordinal)
            || fileName.EndsWith(".tar.bz", StringComparison.Ordinal)
            || fileName.EndsWith(".tar.bz2", StringComparison.Ordinal);
    }

    public static string GetArchiveFormat(string filePath)
    {
        var fileName = Path.GetFileName(filePath).ToLowerInvariant();
        return fileName switch
        {
            _ when fileName.EndsWith(".tar.gz", StringComparison.Ordinal) => "tar.gz",
            _ when fileName.EndsWith(".tar.bz", StringComparison.Ordinal) => "tar.bz",
            _ when fileName.EndsWith(".tar.bz2", StringComparison.Ordinal) => "tar.bz2",
            _ when fileName.EndsWith(".tgz", StringComparison.Ordinal) => "tgz",
            _ when fileName.EndsWith(".tbz", StringComparison.Ordinal) => "tbz",
            _ when fileName.EndsWith(".tbz2", StringComparison.Ordinal) => "tbz2",
            _ when fileName.EndsWith(".zip", StringComparison.Ordinal) => "zip",
            _ when fileName.EndsWith(".7z", StringComparison.Ordinal) => "7z",
            _ when fileName.EndsWith(".rar", StringComparison.Ordinal) => "rar",
            _ when fileName.EndsWith(".tar", StringComparison.Ordinal) => "tar",
            _ when fileName.EndsWith(".gz", StringComparison.Ordinal) => "gz",
            _ when fileName.EndsWith(".bz", StringComparison.Ordinal) => "bz",
            _ when fileName.EndsWith(".bz2", StringComparison.Ordinal) => "bz2",
            _ => Unknown,
        };
    }

    public static string FileDialogFilter =>
        $"支持的压缩包 ({SupportedExtensions})|{SupportedExtensions}|所有文件 (*.*)|*.*";
}
