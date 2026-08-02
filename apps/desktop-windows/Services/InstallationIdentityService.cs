using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PasswordDetective.Desktop.Models;

namespace PasswordDetective.Desktop.Services;

public sealed class InstallationIdentityService : IInstallationIdentityService
{
    private const string KeyAlgorithm = "ecdsa-p256-sha256";
    private static readonly byte[] OptionalEntropy = Encoding.UTF8.GetBytes(
        "PasswordDetective.Desktop.InstallationIdentity.v1");
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
    };

    private readonly string _identityPath;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public InstallationIdentityService(string? identityPath = null)
    {
        _identityPath = identityPath ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PasswordDetective",
            "installation-identity.json");
    }

    public async Task<InstallationIdentity> GetOrCreateAsync(
        CancellationToken cancellationToken = default)
    {
        EnsureWindows();
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var stored = await LoadAsync(cancellationToken);
            if (stored is null)
            {
                stored = await CreateAndStoreAsync(cancellationToken);
            }

            return ToPublicIdentity(stored);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<InstallationIdentity> RegenerateAsync(
        CancellationToken cancellationToken = default)
    {
        EnsureWindows();
        await _gate.WaitAsync(cancellationToken);
        try
        {
            File.Delete(_identityPath + ".tmp");
            var stored = await CreateAndStoreAsync(cancellationToken);
            return ToPublicIdentity(stored);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<string> SignAsync(
        ReadOnlyMemory<byte> canonicalPayload,
        CancellationToken cancellationToken = default)
    {
        EnsureWindows();
        await _gate.WaitAsync(cancellationToken);
        byte[]? privateKey = null;
        try
        {
            var stored = await LoadAsync(cancellationToken)
                ?? await CreateAndStoreAsync(cancellationToken);
            privateKey = ProtectedData.Unprotect(
                Convert.FromBase64String(stored.ProtectedPrivateKey),
                OptionalEntropy,
                DataProtectionScope.CurrentUser);

            using var ecdsa = ECDsa.Create();
            ecdsa.ImportPkcs8PrivateKey(privateKey, out var bytesRead);
            if (bytesRead != privateKey.Length)
            {
                throw new CryptographicException("安装私钥格式无效。");
            }

            var signature = ecdsa.SignData(
                canonicalPayload.Span,
                HashAlgorithmName.SHA256,
                DSASignatureFormat.Rfc3279DerSequence);
            return Convert.ToBase64String(signature);
        }
        finally
        {
            if (privateKey is not null)
            {
                CryptographicOperations.ZeroMemory(privateKey);
            }
            _gate.Release();
        }
    }

    private async Task<StoredInstallationIdentity?> LoadAsync(CancellationToken cancellationToken)
    {
        if (!File.Exists(_identityPath))
        {
            return null;
        }

        await using var stream = new FileStream(
            _identityPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            4096,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        var stored = await JsonSerializer.DeserializeAsync<StoredInstallationIdentity>(
            stream,
            JsonOptions,
            cancellationToken);
        ValidateStoredIdentity(stored);
        return stored;
    }

    private async Task<StoredInstallationIdentity> CreateAndStoreAsync(
        CancellationToken cancellationToken)
    {
        using var ecdsa = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var privateKey = ecdsa.ExportPkcs8PrivateKey();
        try
        {
            var publicKey = ecdsa.ExportSubjectPublicKeyInfo();
            var protectedPrivateKey = ProtectedData.Protect(
                privateKey,
                OptionalEntropy,
                DataProtectionScope.CurrentUser);
            var stored = new StoredInstallationIdentity(
                Guid.NewGuid(),
                Convert.ToBase64String(publicKey),
                Convert.ToBase64String(protectedPrivateKey),
                KeyAlgorithm,
                DateTimeOffset.UtcNow);

            var directory = Path.GetDirectoryName(_identityPath)
                ?? throw new InvalidOperationException("安装身份存储路径无效。");
            Directory.CreateDirectory(directory);
            var temporaryPath = _identityPath + ".tmp";
            await File.WriteAllTextAsync(
                temporaryPath,
                JsonSerializer.Serialize(stored, JsonOptions),
                Encoding.UTF8,
                cancellationToken);
            File.Move(temporaryPath, _identityPath, overwrite: true);
            return stored;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(privateKey);
        }
    }

    private static InstallationIdentity ToPublicIdentity(StoredInstallationIdentity stored)
    {
        var publicKey = Convert.FromBase64String(stored.PublicKey);
        return new InstallationIdentity(
            stored.InstallationId,
            stored.PublicKey,
            Convert.ToHexString(SHA256.HashData(publicKey)).ToLowerInvariant(),
            stored.KeyAlgorithm,
            stored.CreatedAt);
    }

    private static void ValidateStoredIdentity(StoredInstallationIdentity? stored)
    {
        if (stored is null
            || stored.InstallationId == Guid.Empty
            || stored.KeyAlgorithm != KeyAlgorithm
            || string.IsNullOrWhiteSpace(stored.PublicKey)
            || string.IsNullOrWhiteSpace(stored.ProtectedPrivateKey))
        {
            throw new InvalidDataException("安装身份文件无效，请删除后重新启动客户端。");
        }

        _ = Convert.FromBase64String(stored.PublicKey);
        _ = Convert.FromBase64String(stored.ProtectedPrivateKey);
    }

    private static void EnsureWindows()
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("安装身份仅支持 Windows DPAPI。");
        }
    }

    private sealed record StoredInstallationIdentity(
        Guid InstallationId,
        string PublicKey,
        string ProtectedPrivateKey,
        string KeyAlgorithm,
        DateTimeOffset CreatedAt);
}
