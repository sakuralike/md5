using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PasswordDetective.Desktop.Models;

namespace PasswordDetective.Desktop.Services;

public sealed class ProtectedSessionStore : IProtectedSessionStore
{
    private static readonly byte[] OptionalEntropy = Encoding.UTF8.GetBytes(
        "PasswordDetective.Desktop.Session.v1");
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly string _sessionPath;

    public ProtectedSessionStore(string? sessionPath = null)
    {
        _sessionPath = sessionPath ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PasswordDetective",
            "desktop-session.dat");
    }

    public async Task<DesktopSession?> LoadAsync(CancellationToken cancellationToken = default)
    {
        if (!File.Exists(_sessionPath))
        {
            return null;
        }

        var protectedBytes = await File.ReadAllBytesAsync(_sessionPath, cancellationToken);
        var plaintext = ProtectedData.Unprotect(
            protectedBytes,
            OptionalEntropy,
            DataProtectionScope.CurrentUser);
        try
        {
            return JsonSerializer.Deserialize<DesktopSession>(plaintext, JsonOptions)
                ?? throw new InvalidDataException("桌面会话文件无效。");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plaintext);
        }
    }

    public async Task SaveAsync(
        DesktopSession session,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(session);
        var plaintext = JsonSerializer.SerializeToUtf8Bytes(session, JsonOptions);
        try
        {
            var protectedBytes = ProtectedData.Protect(
                plaintext,
                OptionalEntropy,
                DataProtectionScope.CurrentUser);
            var directory = Path.GetDirectoryName(_sessionPath)
                ?? throw new InvalidOperationException("桌面会话存储路径无效。");
            Directory.CreateDirectory(directory);
            var temporaryPath = _sessionPath + ".tmp";
            await File.WriteAllBytesAsync(temporaryPath, protectedBytes, cancellationToken);
            File.Move(temporaryPath, _sessionPath, overwrite: true);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plaintext);
        }
    }

    public void Clear()
    {
        if (File.Exists(_sessionPath))
        {
            File.Delete(_sessionPath);
        }
    }
}
