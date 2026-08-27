using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Security;
using PasswordDetective.Desktop.Plugins.Installation;
using PasswordDetective.Desktop.Plugins.Market;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Permissions;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Runtime;
using PasswordDetective.Desktop.Plugins.Safety;
using PasswordDetective.Desktop.Plugins.Storage;
using PasswordDetective.Desktop.Plugins.UI;
using PasswordDetective.Desktop.Plugins.ViewModels;
using PasswordDetective.Desktop.Services;

namespace PasswordDetective.Desktop.Tests;

public sealed class PluginMarketTests
{
    private readonly string _directory = Path.Combine(
        Path.GetTempPath(),
        "password-detective-market-tests",
        Guid.NewGuid().ToString("N"));

    [Fact]
    public void SemverSelectionUsesNumericComponents()
    {
        var latest = PluginSemver.LatestOrDefault(
        [
            CreateVersion("1.9.0"),
            CreateVersion("1.10.0"),
        ]);

        Assert.NotNull(latest);
        Assert.Equal("1.10.0", latest!.Semver);
    }

    [Fact]
    public void UpdateDiscoveryIncludesOnlyNewerStableMarketVersions()
    {
        var marketPlugin = CreateInstalledPlugin(
            "com.synthetic.market",
            "1.9.0",
            PluginSource.MarketReviewed);
        var localPlugin = CreateInstalledPlugin(
            "com.synthetic.local",
            "1.0.0",
            PluginSource.LocalUnreviewed);
        var catalog = new[]
        {
            CreateCatalogItem("com.synthetic.market", "1.10.0"),
            CreateCatalogItem("com.synthetic.local", "2.0.0"),
        };

        var updates = PluginMarketplaceViewModel.FindPluginUpdates(
            [marketPlugin, localPlugin],
            catalog);

        var update = Assert.Single(updates);
        Assert.Equal("com.synthetic.market", update.PluginSlug);
        Assert.Equal("1.9.0 -> 1.10.0", update.VersionSummary);
        Assert.Equal("available", update.State);

        Assert.Empty(PluginMarketplaceViewModel.FindPluginUpdates(
            [marketPlugin],
            catalog,
            revokedVersions: new HashSet<string>(
                ["com.synthetic.market@1.10.0"],
                StringComparer.Ordinal)));
    }

    [Fact]
    public async Task UpdateCheckLoadsCatalogAndBuildsRetryableQueue()
    {
        var paths = new PluginStoragePaths(Path.Combine(_directory, "update-check"));
        var registry = new PluginRegistry(paths);
        await registry.UpsertAsync(CreateInstalledPlugin(
            "com.synthetic.market",
            "1.9.0",
            PluginSource.MarketReviewed));
        var handler = new CatalogHandler(CreateCatalogItem("com.synthetic.market", "1.10.0"));
        using var httpClient = new HttpClient(handler);
        using var apiClient = new DesktopApiClient(httpClient);
        var permissions = new PluginPermissionPolicy();
        var logs = new PluginLogStore(paths);
        var execution = new PluginExecutionService(paths, logs);
        var safeMode = new PluginSafeMode(paths);
        var installer = new PluginInstaller(
            paths,
            new PluginPackageVerifier(),
            permissions,
            registry,
            execution);
        var viewModel = new PluginMarketplaceViewModel(
            paths,
            installer,
            permissions,
            registry,
            new PluginRuntimeService(registry, execution, safeMode, logs),
            safeMode,
            new RejectingDialogService(),
            "http://localhost/api/v1/",
            logs,
            apiClient);

        await viewModel.CheckPluginUpdatesAsync();

        Assert.Single(viewModel.PluginUpdates);
        Assert.Equal("1.10.0", viewModel.SelectedPluginUpdate?.TargetVersion);
        Assert.Contains("1 个", viewModel.PluginUpdateSummary);
        Assert.Contains("page=1", handler.LastRequestUri?.Query);
        Assert.Contains("page_size=100", handler.LastRequestUri?.Query);
    }

    [Fact]
    public async Task InstallEvidenceUsesAuthenticatedPrivacyMinimizedPayload()
    {
        var handler = new InstallEventHandler();
        using var httpClient = new HttpClient(handler);
        using var apiClient = new DesktopApiClient(httpClient);
        var permission = new PluginPermissionEvidencePayload(
            ["storage:private", "ui:command"],
            ["storage:private", "ui:command"],
            ["ui:command"],
            new string('a', 64),
            "standard",
            DateTimeOffset.Parse("2026-08-28T00:00:00Z"));
        var migration = new PluginMigrationEvidencePayload(
            "1.0.0",
            "1.1.0",
            "completed",
            DateTimeOffset.Parse("2026-08-28T00:00:01Z"),
            DateTimeOffset.Parse("2026-08-28T00:00:02Z"),
            [new PluginMigrationStepEvidencePayload("settings.copy", "completed", 2)]);
        var payload = new PluginInstallEventRequest(
            "synthetic-install-evidence-001",
            "com.synthetic.market",
            "1.1.0",
            "windows-x64",
            PluginSource.MarketReviewed,
            "upgraded",
            "success",
            "0.1.0",
            permission,
            migration,
            Guid.Parse("11111111-1111-1111-1111-111111111111"),
            "synthetic-evidence-signature");

        await apiClient.RecordPluginInstallEventAsync(
            "http://localhost/api/v1/",
            payload,
            "synthetic-access-token");

        var canonical = Encoding.UTF8.GetString(PluginInstallEvidenceCanonicalizer.Build(payload));
        Assert.Contains("version=desktop-plugin-install-evidence-v1\n", canonical);
        Assert.Contains("installation_id=11111111-1111-1111-1111-111111111111\n", canonical);
        Assert.Contains("consented_at=2026-08-28T00:00:00.000Z\n", canonical);
        Assert.Contains("migration_steps=settings.copy:completed:2\n", canonical);
        Assert.Equal("Bearer", handler.AuthorizationScheme);
        Assert.Equal("synthetic-access-token", handler.AuthorizationParameter);
        Assert.Contains("\"permission_evidence\"", handler.RequestBody);
        Assert.Contains("\"migration_evidence\"", handler.RequestBody);
        Assert.Contains("\"installation_id\"", handler.RequestBody);
        Assert.DoesNotContain("error", handler.RequestBody, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("path", handler.RequestBody, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CanaryTicketAndDownloadUseAuthenticatedDeviceBinding()
    {
        var installationId = Guid.Parse("22222222-2222-2222-2222-222222222222");
        var artifact = Encoding.UTF8.GetBytes("synthetic-canary-artifact");
        var handler = new CanaryDownloadHandler(artifact);
        using var httpClient = new HttpClient(handler);
        using var apiClient = new DesktopApiClient(httpClient);

        var ticket = await apiClient.IssueCanaryPluginDownloadTicketAsync(
            "http://localhost/api/v1/",
            "synthetic-admin-token",
            "synthetic-version-id",
            "windows-x64",
            installationId,
            "synthetic-ticket-signature");
        Directory.CreateDirectory(_directory);
        var destination = Path.Combine(_directory, $"canary-{Guid.NewGuid():N}.pdpkg");
        await apiClient.DownloadPluginArtifactAsync(
            ticket.DownloadUrl,
            destination,
            Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(artifact)),
            artifact.LongLength,
            accessToken: "synthetic-admin-token",
            installationId: installationId,
            canarySignature: "synthetic-download-signature");

        Assert.Equal(artifact, await File.ReadAllBytesAsync(destination));
        Assert.Equal("synthetic-admin-token", handler.TicketBearer);
        Assert.Contains("\"installation_id\"", handler.TicketBody);
        Assert.Equal("synthetic-admin-token", handler.DownloadBearer);
        Assert.Equal(installationId.ToString("D"), handler.DownloadInstallationId);
        Assert.Equal("synthetic-download-signature", handler.DownloadSignature);
        var ticketCanonical = Encoding.UTF8.GetString(
            PluginCanaryCanonicalizer.BuildTicketRequest(
                "synthetic-version-id",
                "windows-x64",
                installationId));
        Assert.Contains("version=desktop-plugin-canary-ticket-v1\n", ticketCanonical);
        Assert.Contains("installation_id=22222222-2222-2222-2222-222222222222\n", ticketCanonical);
    }

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
            "合成测试发布说明",
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

    private static MarketPluginVersion CreateVersion(string semver) => new(
        "version-id-" + semver,
        "com.synthetic.market",
        semver,
        JsonDocument.Parse("{}").RootElement.Clone(),
        "a".PadRight(64, 'a'),
        "b".PadRight(64, 'b'),
        ["ui:command"],
        "standard",
        "release notes",
        "desktop-plugin-static-review-v1",
        "platform-ed25519-synthetic",
        Convert.ToBase64String(new byte[32]),
        Convert.ToBase64String(new byte[64]),
        JsonDocument.Parse("{}").RootElement.Clone(),
        DateTimeOffset.UtcNow,
        []);

    private static MarketPluginCatalogItem CreateCatalogItem(string slug, string version) => new(
        slug,
        slug,
        "合成开发者",
        "合成插件更新",
        "development",
        [],
        version,
        "standard",
        "desktop-plugin-static-review-v1",
        DateTimeOffset.UtcNow,
        ["windows-x64"]);

    private static InstalledPlugin CreateInstalledPlugin(
        string pluginId,
        string version,
        string source)
    {
        var manifest = new PluginManifest(
            PluginPackageVerifier.ManifestSchema,
            pluginId,
            version,
            pluginId,
            "合成插件",
            "synthetic-key",
            Convert.ToBase64String(new byte[32]),
            new PluginProtocolRange(1, 1),
            new PluginHostRange("0.1.0", "0.x"),
            new PluginRuntimeManifest(
                "process",
                new Dictionary<string, string>
                {
                    ["windows-x64"] = "bin/windows-x64/plugin.exe",
                }),
            [new PluginCommandManifest("echo", "回显", "schemas/echo.schema.json")],
            new PluginCapabilitiesManifest(["ui:command"], []),
            new PluginLimitsManifest(128, 25, 30, 0));
        var installed = new InstalledPlugin(
            pluginId,
            pluginId,
            "合成插件",
            "synthetic-key",
            "synthetic-fingerprint",
            source,
            version,
            null,
            new Dictionary<string, InstalledPluginVersion>(StringComparer.Ordinal)
            {
                [version] = new InstalledPluginVersion(
                    version,
                    new string('a', 64),
                    "bin/windows-x64/plugin.exe",
                    manifest,
                    DateTimeOffset.UtcNow),
            },
            ["ui:command"],
            true,
            0,
            "ready",
            null,
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow,
            null);
        return source == PluginSource.MarketReviewed
            ? installed with
            {
                PlatformKeyId = "platform-key",
                PlatformPublicKeyBase64 = Convert.ToBase64String(new byte[32]),
                PlatformSignatureBase64 = Convert.ToBase64String(new byte[64]),
                ReviewPolicyVersion = "desktop-plugin-static-review-v1",
            }
            : installed;
    }

    private sealed class CatalogHandler(MarketPluginCatalogItem item) : HttpMessageHandler
    {
        public Uri? LastRequestUri { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            LastRequestUri = request.RequestUri;
            var content = JsonSerializer.Serialize(new MarketPluginCatalogResponse([item], 1, 100, 1));
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(content, Encoding.UTF8, "application/json"),
            });
        }
    }

    private sealed class InstallEventHandler : HttpMessageHandler
    {
        public string? AuthorizationScheme { get; private set; }
        public string? AuthorizationParameter { get; private set; }
        public string RequestBody { get; private set; } = string.Empty;

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            AuthorizationScheme = request.Headers.Authorization?.Scheme;
            AuthorizationParameter = request.Headers.Authorization?.Parameter;
            RequestBody = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(HttpStatusCode.Accepted)
            {
                Content = new StringContent(
                    "{\"accepted\":true,\"event_id\":\"synthetic-install-evidence-001\"}",
                    Encoding.UTF8,
                    "application/json"),
            };
        }
    }

    private sealed class CanaryDownloadHandler(byte[] artifact) : HttpMessageHandler
    {
        public string? TicketBearer { get; private set; }
        public string TicketBody { get; private set; } = string.Empty;
        public string? DownloadBearer { get; private set; }
        public string? DownloadInstallationId { get; private set; }
        public string? DownloadSignature { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.Method == HttpMethod.Post)
            {
                TicketBearer = request.Headers.Authorization?.Parameter;
                TicketBody = request.Content is null
                    ? string.Empty
                    : await request.Content.ReadAsStringAsync(cancellationToken);
                var body = JsonSerializer.Serialize(new MarketPluginDownloadTicket(
                    "http://localhost/api/v1/desktop/plugins/downloads/synthetic-canary-token",
                    DateTimeOffset.UtcNow.AddMinutes(5),
                    Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(artifact)),
                    artifact.LongLength));
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(body, Encoding.UTF8, "application/json"),
                };
            }

            DownloadBearer = request.Headers.Authorization?.Parameter;
            DownloadInstallationId = request.Headers.TryGetValues(
                "X-Plugin-Installation-Id",
                out var installationValues)
                ? installationValues.Single()
                : null;
            DownloadSignature = request.Headers.TryGetValues(
                "X-Plugin-Canary-Signature",
                out var signatureValues)
                ? signatureValues.Single()
                : null;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(artifact),
            };
        }
    }

    private sealed class RejectingDialogService : IPluginDialogService
    {
        public string? SelectPackage() => null;
        public string? SelectPath(PasswordDetective.Desktop.Plugins.ViewModels.PluginCommandFieldKind kind) => null;
        public bool ConfirmInstall(
            PluginPackageInspection inspection,
            PluginPermissionDecision permission) => false;
        public bool ConfirmMarketInstall(
            MarketPluginDetail detail,
            MarketPluginVersion version,
            PluginPermissionDecision permission,
            string? currentVersion,
            string? currentRiskTier,
            IReadOnlyList<string> addedCapabilities,
            bool signingKeyChanged,
            bool majorVersionChanged) => false;
        public bool ConfirmUninstall(InstalledPlugin plugin) => false;
    }
}
