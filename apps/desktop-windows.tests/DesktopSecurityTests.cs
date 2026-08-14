using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PasswordDetective.Desktop.Protocol;
using PasswordDetective.Desktop.Services;

namespace PasswordDetective.Desktop.Tests;

public sealed class DesktopSecurityTests : IDisposable
{
    private readonly string _temporaryDirectory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-tests",
        Guid.NewGuid().ToString("N"));

    public DesktopSecurityTests() => Directory.CreateDirectory(_temporaryDirectory);

    [Fact]
    public void CanonicalReceiptPayloadMatchesServerProtocol()
    {
        var payload = new DesktopReceiptPayload(
            "11111111-1111-1111-1111-111111111111",
            "synthetic-challenge-nonce",
            Guid.Parse("22222222-2222-2222-2222-222222222222"),
            "33333333-3333-3333-3333-333333333333",
            "44444444-4444-4444-4444-444444444444",
            "sha256",
            new string('a', 64),
            new string('b', 64),
            "success",
            "zip",
            "0.1.0",
            new DateTimeOffset(2026, 8, 2, 1, 2, 3, 456, TimeSpan.Zero));

        var actual = Encoding.UTF8.GetString(DesktopReceiptCanonicalizer.Build(payload));

        Assert.Equal(
            "version=desktop-receipt-v1\n" +
            "challenge_id=11111111-1111-1111-1111-111111111111\n" +
            "challenge_nonce=synthetic-challenge-nonce\n" +
            "installation_id=22222222-2222-2222-2222-222222222222\n" +
            "account_id=33333333-3333-3333-3333-333333333333\n" +
            "candidate_id=44444444-4444-4444-4444-444444444444\n" +
            "fingerprint_algorithm=sha256\n" +
            $"fingerprint_digest={new string('a', 64)}\n" +
            $"candidate_digest={new string('b', 64)}\n" +
            "outcome=success\n" +
            "archive_format=zip\n" +
            "client_version=0.1.0\n" +
            "verified_at=2026-08-02T01:02:03.456Z\n",
            actual);
    }

    [Fact]
    public async Task InstallationIdentityPersistsAndProducesDerEcdsaSignature()
    {
        var path = Path.Combine(_temporaryDirectory, "identity.json");
        var firstService = new InstallationIdentityService(path);
        var first = await firstService.GetOrCreateAsync();
        var signature = Convert.FromBase64String(
            await firstService.SignAsync(Encoding.UTF8.GetBytes("synthetic-payload")));
        var second = await new InstallationIdentityService(path).GetOrCreateAsync();

        Assert.Equal(first.InstallationId, second.InstallationId);
        Assert.Equal(first.PublicKey, second.PublicKey);
        using var publicKey = ECDsa.Create();
        publicKey.ImportSubjectPublicKeyInfo(Convert.FromBase64String(first.PublicKey), out _);
        Assert.True(publicKey.VerifyData(
            Encoding.UTF8.GetBytes("synthetic-payload"),
            signature,
            HashAlgorithmName.SHA256,
            DSASignatureFormat.Rfc3279DerSequence));
        Assert.DoesNotContain("PRIVATE KEY", await File.ReadAllTextAsync(path));
    }

    [Fact]
    public async Task InstallationIdentityCanBeRegeneratedAndOldSignatureStopsMatching()
    {
        var path = Path.Combine(_temporaryDirectory, "identity-regenerated.json");
        var service = new InstallationIdentityService(path);
        var payload = Encoding.UTF8.GetBytes("synthetic-regeneration-payload");
        var first = await service.GetOrCreateAsync();
        var firstSignature = Convert.FromBase64String(await service.SignAsync(payload));

        var replacement = await service.RegenerateAsync();
        var replacementSignature = Convert.FromBase64String(await service.SignAsync(payload));
        var persisted = await new InstallationIdentityService(path).GetOrCreateAsync();

        Assert.NotEqual(first.InstallationId, replacement.InstallationId);
        Assert.NotEqual(first.PublicKey, replacement.PublicKey);
        Assert.Equal(replacement, persisted);
        using var replacementPublicKey = ECDsa.Create();
        replacementPublicKey.ImportSubjectPublicKeyInfo(
            Convert.FromBase64String(replacement.PublicKey),
            out _);
        Assert.False(replacementPublicKey.VerifyData(
            payload,
            firstSignature,
            HashAlgorithmName.SHA256,
            DSASignatureFormat.Rfc3279DerSequence));
        Assert.True(replacementPublicKey.VerifyData(
            payload,
            replacementSignature,
            HashAlgorithmName.SHA256,
            DSASignatureFormat.Rfc3279DerSequence));
    }

    [Fact]
    public void DesktopRecoveryAdvisorExplainsIdentityAndUpgradeRecovery()
    {
        var revoked = DesktopRecoveryAdvisor.From(new DesktopApiException(
            409,
            "desktop.installation_revoked",
            "synthetic revoked response"));
        var upgrade = DesktopRecoveryAdvisor.From(new DesktopApiException(
            426,
            "desktop.client_version_unsupported",
            "synthetic version response",
            new Dictionary<string, JsonElement>
            {
                ["minimum_client_version"] = JsonSerializer.SerializeToElement("0.2.0"),
            }));

        Assert.True(revoked.CanRegenerateInstallation);
        Assert.False(revoked.UpgradeRequired);
        Assert.Contains("新的安装身份", revoked.Message);
        Assert.False(upgrade.CanRegenerateInstallation);
        Assert.True(upgrade.UpgradeRequired);
        Assert.Contains("0.2.0", upgrade.Message);
    }

    [Fact]
    public async Task ArchiveVerificationReadsContentAndRejectsTraversalEntry()
    {
        var validPath = Path.Combine(_temporaryDirectory, "valid.zip");
        using (var archive = ZipFile.Open(validPath, ZipArchiveMode.Create))
        {
            var entry = archive.CreateEntry("folder/synthetic.txt");
            await using var writer = entry.Open();
            await writer.WriteAsync(Encoding.UTF8.GetBytes("synthetic archive content"));
        }

        var service = new ArchiveVerificationService();
        var valid = await service.VerifyAsync(validPath, "synthetic-password");
        Assert.False(valid.Success);
        Assert.True(valid.BytesSampled > 0);
        Assert.Contains("未检测到", valid.Message);

        var unsafePath = Path.Combine(_temporaryDirectory, "unsafe.zip");
        using (var archive = ZipFile.Open(unsafePath, ZipArchiveMode.Create))
        {
            var entry = archive.CreateEntry("../escape.txt");
            await using var writer = entry.Open();
            await writer.WriteAsync(Encoding.UTF8.GetBytes("synthetic unsafe content"));
        }
        var rejected = await service.VerifyAsync(unsafePath, "synthetic-password");
        Assert.False(rejected.Success);
        Assert.Contains("路径", rejected.Message);
    }

    public void Dispose()
    {
        if (Directory.Exists(_temporaryDirectory))
        {
            Directory.Delete(_temporaryDirectory, recursive: true);
        }
    }
}
