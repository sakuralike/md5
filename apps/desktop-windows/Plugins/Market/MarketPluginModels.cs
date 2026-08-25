using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Encodings.Web;
using System.Text.Json.Serialization;
using PasswordDetective.Desktop.Plugins.Packages;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;

namespace PasswordDetective.Desktop.Plugins.Market;

public sealed record MarketPluginArtifact(
    [property: JsonPropertyName("architecture")] string Architecture,
    [property: JsonPropertyName("size_bytes")] long SizeBytes,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("artifact_filename")] string ArtifactFilename);

public sealed record MarketPluginVersion(
    [property: JsonPropertyName("version_id")] string VersionId,
    [property: JsonPropertyName("plugin_slug")] string PluginSlug,
    [property: JsonPropertyName("semver")] string Semver,
    [property: JsonPropertyName("manifest_json")] JsonElement ManifestJson,
    [property: JsonPropertyName("manifest_sha256")] string ManifestSha256,
    [property: JsonPropertyName("signing_key_fingerprint")] string SigningKeyFingerprint,
    [property: JsonPropertyName("approved_capabilities")] IReadOnlyList<string> ApprovedCapabilities,
    [property: JsonPropertyName("risk_tier")] string RiskTier,
    [property: JsonPropertyName("review_policy_version")] string ReviewPolicyVersion,
    [property: JsonPropertyName("platform_key_id")] string PlatformKeyId,
    [property: JsonPropertyName("platform_public_key_base64")] string PlatformPublicKeyBase64,
    [property: JsonPropertyName("platform_signature_base64")] string PlatformSignatureBase64,
    [property: JsonPropertyName("platform_signature_payload")] JsonElement PlatformSignaturePayload,
    [property: JsonPropertyName("published_at")] DateTimeOffset PublishedAt,
    [property: JsonPropertyName("artifacts")] IReadOnlyList<MarketPluginArtifact> Artifacts);

public sealed record MarketPluginDetail(
    [property: JsonPropertyName("slug")] string Slug,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("developer_name")] string DeveloperName,
    [property: JsonPropertyName("summary")] string Summary,
    [property: JsonPropertyName("description")] string Description,
    [property: JsonPropertyName("category")] string Category,
    [property: JsonPropertyName("tags")] IReadOnlyList<string> Tags,
    [property: JsonPropertyName("versions")] IReadOnlyList<MarketPluginVersion> Versions);

public sealed record MarketPluginCatalogItem(
    [property: JsonPropertyName("slug")] string Slug,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("developer_name")] string DeveloperName,
    [property: JsonPropertyName("summary")] string Summary,
    [property: JsonPropertyName("category")] string Category,
    [property: JsonPropertyName("tags")] IReadOnlyList<string> Tags,
    [property: JsonPropertyName("latest_version")] string LatestVersion,
    [property: JsonPropertyName("risk_tier")] string RiskTier,
    [property: JsonPropertyName("review_policy_version")] string ReviewPolicyVersion,
    [property: JsonPropertyName("published_at")] DateTimeOffset PublishedAt,
    [property: JsonPropertyName("architectures")] IReadOnlyList<string> Architectures);

public sealed record MarketPluginCatalogResponse(
    [property: JsonPropertyName("items")] IReadOnlyList<MarketPluginCatalogItem> Items,
    [property: JsonPropertyName("page")] int Page,
    [property: JsonPropertyName("page_size")] int PageSize,
    [property: JsonPropertyName("total")] int Total);

public sealed record MarketPluginDownloadTicket(
    [property: JsonPropertyName("download_url")] string DownloadUrl,
    [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt,
    [property: JsonPropertyName("artifact_sha256")] string ArtifactSha256,
    [property: JsonPropertyName("artifact_size_bytes")] long ArtifactSizeBytes);

public sealed record MarketPluginRevocation(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("scope")] string Scope,
    [property: JsonPropertyName("plugin_slug")] string? PluginSlug,
    [property: JsonPropertyName("semver")] string? Semver,
    [property: JsonPropertyName("signing_key_fingerprint")] string? SigningKeyFingerprint,
    [property: JsonPropertyName("reason_code")] string ReasonCode,
    [property: JsonPropertyName("affects_historical_versions")] bool AffectsHistoricalVersions,
    [property: JsonPropertyName("effective_at")] DateTimeOffset EffectiveAt,
    [property: JsonPropertyName("platform_key_id")] string PlatformKeyId,
    [property: JsonPropertyName("platform_public_key_base64")] string PlatformPublicKeyBase64,
    [property: JsonPropertyName("platform_signature_base64")] string PlatformSignatureBase64,
    [property: JsonPropertyName("platform_signature_payload")] JsonElement PlatformSignaturePayload);

public sealed record MarketPluginRevocationList(
    [property: JsonPropertyName("generated_at")] DateTimeOffset GeneratedAt,
    [property: JsonPropertyName("policy_version")] string PolicyVersion,
    [property: JsonPropertyName("items")] IReadOnlyList<MarketPluginRevocation> Items);

public static class PlatformSignatureVerifier
{
    public static void Verify(MarketPluginVersion version)
    {
        var publicKey = Convert.FromBase64String(version.PlatformPublicKeyBase64);
        var signature = Convert.FromBase64String(version.PlatformSignatureBase64);
        var expectedKeyId = $"platform-ed25519-{Convert.ToHexString(SHA256.HashData(publicKey)).ToLowerInvariant()[..16]}";
        if (!string.Equals(expectedKeyId, version.PlatformKeyId, StringComparison.Ordinal))
        {
            throw new PluginPackageException("平台签章密钥 ID 与公钥不一致。");
        }

        if (!VerifyEd25519(signature, CanonicalJson.Serialize(version.PlatformSignaturePayload), publicKey)
            || !MatchesVersionPayload(version))
        {
            throw new PluginPackageException("平台审核签章无效。");
        }
    }

    public static void Verify(MarketPluginRevocation revocation)
    {
        var publicKey = Convert.FromBase64String(revocation.PlatformPublicKeyBase64);
        var signature = Convert.FromBase64String(revocation.PlatformSignatureBase64);
        var expectedKeyId = $"platform-ed25519-{Convert.ToHexString(SHA256.HashData(publicKey)).ToLowerInvariant()[..16]}";
        if (!string.Equals(expectedKeyId, revocation.PlatformKeyId, StringComparison.Ordinal)
            || !VerifyEd25519(signature, CanonicalJson.Serialize(revocation.PlatformSignaturePayload), publicKey)
            || !MatchesRevocationPayload(revocation))
        {
            throw new PluginPackageException("平台撤销签章无效。");
        }
    }

    private static bool MatchesVersionPayload(MarketPluginVersion version)
    {
        var payload = version.PlatformSignaturePayload;
        if (payload.ValueKind != JsonValueKind.Object
            || !TryString(payload, "plugin_slug", out var slug)
            || !TryString(payload, "semver", out var semver)
            || !TryString(payload, "manifest_sha256", out var manifestSha256)
            || !TryString(payload, "policy", out var policy)
            || !TryString(payload, "published_at", out var publishedAt)
            || !string.Equals(slug, version.PluginSlug, StringComparison.Ordinal)
            || !string.Equals(semver, version.Semver, StringComparison.Ordinal)
            || !string.Equals(manifestSha256, version.ManifestSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(policy, version.ReviewPolicyVersion, StringComparison.Ordinal)
            || !DateTimeOffset.TryParse(publishedAt, out var parsedPublishedAt)
            || Math.Abs((parsedPublishedAt - version.PublishedAt).TotalSeconds) > 1)
        {
            return false;
        }

        if (!TryStringArray(payload, "approved_capabilities", out var capabilities)
            || !capabilities.SequenceEqual(
                version.ApprovedCapabilities.Order(StringComparer.Ordinal),
                StringComparer.Ordinal))
        {
            return false;
        }

        if (!payload.TryGetProperty("artifacts", out var artifacts)
            || artifacts.ValueKind != JsonValueKind.Array)
        {
            return false;
        }

        var expectedArtifacts = version.Artifacts
            .OrderBy(item => item.Architecture, StringComparer.Ordinal)
            .ToArray();
        var actualArtifacts = artifacts.EnumerateArray().ToArray();
        return actualArtifacts.Length == expectedArtifacts.Length
            && actualArtifacts.Zip(expectedArtifacts).All(pair =>
                TryString(pair.First, "architecture", out var architecture)
                && TryString(pair.First, "sha256", out var sha256)
                && TryInt64(pair.First, "size_bytes", out var sizeBytes)
                && string.Equals(architecture, pair.Second.Architecture, StringComparison.Ordinal)
                && string.Equals(sha256, pair.Second.Sha256, StringComparison.OrdinalIgnoreCase)
                && sizeBytes == pair.Second.SizeBytes);
    }

    private static bool MatchesRevocationPayload(MarketPluginRevocation revocation)
    {
        var payload = revocation.PlatformSignaturePayload;
        if (payload.ValueKind != JsonValueKind.Object
            || !TryString(payload, "scope", out var scope)
            || !TryString(payload, "reason_code", out var reasonCode)
            || !TryString(payload, "effective_at", out var effectiveAt)
            || !string.Equals(scope, revocation.Scope, StringComparison.Ordinal)
            || !string.Equals(reasonCode, revocation.ReasonCode, StringComparison.Ordinal)
            || !DateTimeOffset.TryParse(effectiveAt, out var parsedEffectiveAt)
            || Math.Abs((parsedEffectiveAt - revocation.EffectiveAt).TotalSeconds) > 1
            || !payload.TryGetProperty("affects_historical_versions", out var historical)
            || historical.ValueKind != JsonValueKind.True && historical.ValueKind != JsonValueKind.False
            || historical.GetBoolean() != revocation.AffectsHistoricalVersions)
        {
            return false;
        }

        return revocation.Scope switch
        {
            "plugin" => TryString(payload, "plugin_slug", out var slug)
                && string.Equals(slug, revocation.PluginSlug, StringComparison.Ordinal),
            "version" => TryString(payload, "plugin_slug", out var versionSlug)
                && TryString(payload, "semver", out var semver)
                && string.Equals(versionSlug, revocation.PluginSlug, StringComparison.Ordinal)
                && string.Equals(semver, revocation.Semver, StringComparison.Ordinal),
            "signing_key" => TryString(payload, "signing_key_fingerprint", out var fingerprint)
                && string.Equals(fingerprint, revocation.SigningKeyFingerprint, StringComparison.OrdinalIgnoreCase),
            _ => false,
        };
    }

    private static bool TryString(JsonElement element, string propertyName, out string value)
    {
        if (element.TryGetProperty(propertyName, out var property)
            && property.ValueKind == JsonValueKind.String)
        {
            value = property.GetString() ?? string.Empty;
            return true;
        }

        value = string.Empty;
        return false;
    }

    private static bool TryStringArray(JsonElement element, string propertyName, out string[] values)
    {
        if (element.TryGetProperty(propertyName, out var property)
            && property.ValueKind == JsonValueKind.Array
            && property.EnumerateArray().All(item => item.ValueKind == JsonValueKind.String))
        {
            values = property.EnumerateArray().Select(item => item.GetString() ?? string.Empty).ToArray();
            return true;
        }

        values = [];
        return false;
    }

    private static bool TryInt64(JsonElement element, string propertyName, out long value)
    {
        if (element.TryGetProperty(propertyName, out var property)
            && property.TryGetInt64(out value))
        {
            return true;
        }

        value = 0;
        return false;
    }

    private static bool VerifyEd25519(byte[] signature, byte[] data, byte[] publicKey)
    {
        var verifier = new Ed25519Signer();
        verifier.Init(false, new Ed25519PublicKeyParameters(publicKey, 0));
        verifier.BlockUpdate(data, 0, data.Length);
        return verifier.VerifySignature(signature);
    }
}

internal static class CanonicalJson
{
    private static readonly JsonWriterOptions Options = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        Indented = false,
    };

    public static byte[] Serialize(JsonElement element)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, Options))
        {
            Write(writer, element);
        }

        return stream.ToArray();
    }

    private static void Write(Utf8JsonWriter writer, JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (var property in element.EnumerateObject().OrderBy(item => item.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    Write(writer, property.Value);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (var item in element.EnumerateArray())
                {
                    Write(writer, item);
                }
                writer.WriteEndArray();
                break;
            default:
                element.WriteTo(writer);
                break;
        }
    }
}
