using System.IO;
using System.Text.Json;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Security;
using PasswordDetective.Desktop.Plugins.Market;
using PasswordDetective.Desktop.Plugins.Packages;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginMarketTests
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-market-tests",
        Guid.NewGuid().ToString("N"));

    [Fact]
    public void PlatformSignatureVerifierAcceptsPublicPayloadAndRejectsTampering()
    {
        var privateKey = new Ed25519PrivateKeyParameters(new SecureRandom());
        var publicKey = privateKey.GeneratePublicKey().GetEncoded();
        using var document = JsonDocument.Parse(
            "{\"approved_capabilities\":[\"ui:command\"],\"artifacts\":[],\"manifest_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"plugin_slug\":\"com.synthetic.market\",\"policy\":\"desktop-plugin-static-review-v1\",\"published_at\":\"2026-08-26T00:00:00Z\",\"semver\":\"1.0.0\"}");
        var payload = document.RootElement.Clone();
        var canonical = CanonicalForTest(payload);
        var signer = new Ed25519Signer();
        signer.Init(true, privateKey);
        signer.BlockUpdate(canonical, 0, canonical.Length);
        var signature = signer.GenerateSignature();
        var version = new MarketPluginVersion(
            "version-id",
            "com.synthetic.market",
            "1.0.0",
            JsonDocument.Parse("{}").RootElement.Clone(),
            "a".PadRight(64, 'a'),
            "b".PadRight(64, 'b'),
            ["ui:command"],
            "standard",
            "desktop-plugin-static-review-v1",
            $"platform-ed25519-{Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(publicKey)).ToLowerInvariant()[..16]}",
            Convert.ToBase64String(publicKey),
            Convert.ToBase64String(signature),
            payload,
            DateTimeOffset.Parse("2026-08-26T00:00:00Z"),
            []);

        PlatformSignatureVerifier.Verify(version);
        using var tamperedDocument = JsonDocument.Parse(
            "{\"approved_capabilities\":[\"network:internet\"],\"plugin_slug\":\"com.synthetic.market\",\"published_at\":\"2026-08-26T00:00:00Z\",\"semver\":\"1.0.0\"}");
        var tampered = version with { PlatformSignaturePayload = tamperedDocument.RootElement.Clone() };
        Assert.Throws<PluginPackageException>(() => PlatformSignatureVerifier.Verify(tampered));
    }

    [Fact]
    public async Task RevocationCachePersistsVerifiedFactsAndFailsClosedAfterExpiry()
    {
        var privateKey = new Ed25519PrivateKeyParameters(new SecureRandom());
        var publicKey = privateKey.GeneratePublicKey().GetEncoded();
        using var payloadDocument = JsonDocument.Parse(
            "{\"affects_historical_versions\":true,\"effective_at\":\"2026-08-26T00:00:00Z\",\"reason_code\":\"synthetic\",\"scope\":\"signing_key\",\"signing_key_fingerprint\":\"publisher-fingerprint\"}");
        var payload = payloadDocument.RootElement.Clone();
        var signer = new Ed25519Signer();
        signer.Init(true, privateKey);
        var canonical = CanonicalForTest(payload);
        signer.BlockUpdate(canonical, 0, canonical.Length);
        var revocation = new MarketPluginRevocation(
            "revocation-id",
            "signing_key",
            null,
            null,
            "publisher-fingerprint",
            "synthetic",
            true,
            DateTimeOffset.Parse("2026-08-26T00:00:00Z"),
            $"platform-ed25519-{Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(publicKey)).ToLowerInvariant()[..16]}",
            Convert.ToBase64String(publicKey),
            Convert.ToBase64String(signer.GenerateSignature()),
            payload);
        PlatformSignatureVerifier.Verify(revocation);
        var paths = new PasswordDetective.Desktop.Plugins.Storage.PluginStoragePaths(_directory);
        var cache = new PluginRevocationCache(paths);
        await cache.SaveAsync(
            new MarketPluginRevocationList(
                DateTimeOffset.UtcNow,
                "desktop-plugin-control-plane-v1",
                [revocation]),
            TimeSpan.FromMinutes(5));

        var snapshot = await cache.LoadAsync();

        Assert.NotNull(snapshot);
        Assert.False(snapshot!.IsExpired(DateTimeOffset.UtcNow));
        Assert.Single(snapshot.Items);
        Assert.True(snapshot.IsExpired(snapshot.ExpiresAt));

        await File.WriteAllTextAsync(paths.RevocationCachePath, "{\"items\":[{}]}");
        Assert.Null(await cache.LoadAsync());
    }

    private static byte[] CanonicalForTest(JsonElement element) =>
        System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(
            element,
            new JsonSerializerOptions
            {
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
                WriteIndented = false,
            });
}
