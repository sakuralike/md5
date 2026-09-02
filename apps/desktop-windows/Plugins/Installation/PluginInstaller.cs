using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Market;
using PasswordDetective.Desktop.Plugins.Permissions;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.Runtime;
using PasswordDetective.Desktop.Plugins.Storage;

namespace PasswordDetective.Desktop.Plugins.Installation;

public sealed record PluginInstallResult(
    InstalledPlugin Plugin,
    PluginPackageInspection Inspection,
    IReadOnlyList<string> DeniedOptionalCapabilities);

public sealed class PluginInstallException : Exception
{
    public PluginInstallException(string message) : base(message)
    {
    }

    public PluginInstallException(string message, Exception innerException) : base(message, innerException)
    {
    }
}

public sealed class PluginInstaller
{
    private readonly PluginStoragePaths _paths;
    private readonly PluginPackageVerifier _verifier;
    private readonly PluginPermissionPolicy _permissions;
    private readonly PluginRegistry _registry;
    private readonly IPluginInstallValidator _validator;
    private readonly SemaphoreSlim _lock = new(1, 1);

    public PluginInstaller(
        PluginStoragePaths paths,
        PluginPackageVerifier verifier,
        PluginPermissionPolicy permissions,
        PluginRegistry registry,
        IPluginInstallValidator validator)
    {
        _paths = paths;
        _verifier = verifier;
        _permissions = permissions;
        _registry = registry;
        _validator = validator;
    }

    public Task<PluginPackageInspection> InspectAsync(
        string packagePath,
        CancellationToken cancellationToken = default) =>
        _verifier.VerifyAsync(packagePath, cancellationToken);

    public async Task<PluginInstallResult> InstallMarketAsync(
        string packagePath,
        MarketPluginVersion marketVersion,
        IEnumerable<string> userGrantedCapabilities,
        CancellationToken cancellationToken = default)
    {
        PlatformSignatureVerifier.Verify(marketVersion);
        var inspection = await _verifier.VerifyAsync(packagePath, cancellationToken);
        if (!string.Equals(inspection.Manifest.PluginId, marketVersion.PluginSlug, StringComparison.Ordinal)
            || !string.Equals(inspection.Manifest.Version, marketVersion.Semver, StringComparison.Ordinal)
            || !string.Equals(
                inspection.Files.Single(item => item.Path == PluginPackageVerifier.ManifestPath).Sha256,
                marketVersion.ManifestSha256,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new PluginInstallException("在线插件清单或摘要与平台发布版本不一致。");
        }

        var requestedCapabilities = inspection.Manifest.Capabilities.Required
            .Concat(inspection.Manifest.Capabilities.Optional)
            .ToHashSet(StringComparer.Ordinal);
        var approvedCapabilities = marketVersion.ApprovedCapabilities.ToHashSet(StringComparer.Ordinal);
        if (!approvedCapabilities.IsSubsetOf(requestedCapabilities)
            || inspection.Manifest.Capabilities.Required.Any(
                capability => !approvedCapabilities.Contains(capability)))
        {
            throw new PluginInstallException("平台批准权限不是插件清单申请权限的完整子集。");
        }

        var artifact = marketVersion.Artifacts.SingleOrDefault(
            item => string.Equals(item.Architecture, inspection.Architecture, StringComparison.Ordinal));
        if (artifact is null
            || !string.Equals(artifact.Sha256, inspection.PackageSha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new PluginInstallException("在线插件制品摘要与平台发布版本不一致。");
        }

        var local = await InstallAsync(
            packagePath,
            userGrantedCapabilities.Intersect(approvedCapabilities, StringComparer.Ordinal),
            marketReviewed: true,
            cancellationToken,
            approvedCapabilities,
            marketVersion.RiskTier);
        var market = local.Plugin with
        {
            Source = PluginSource.MarketReviewed,
            PlatformKeyId = marketVersion.PlatformKeyId,
            PlatformPublicKeyBase64 = marketVersion.PlatformPublicKeyBase64,
            PlatformSignatureBase64 = marketVersion.PlatformSignatureBase64,
            ReviewPolicyVersion = marketVersion.ReviewPolicyVersion,
            RiskTier = marketVersion.RiskTier,
        };
        await _registry.UpsertAsync(market, cancellationToken);
        return local with { Plugin = market };
    }

    public Task<PluginInstallResult> InstallLocalAsync(
        string packagePath,
        IEnumerable<string> userGrantedCapabilities,
        CancellationToken cancellationToken = default) =>
        InstallAsync(packagePath, userGrantedCapabilities, marketReviewed: false, cancellationToken);

    private async Task<PluginInstallResult> InstallAsync(
        string packagePath,
        IEnumerable<string> userGrantedCapabilities,
        bool marketReviewed,
        CancellationToken cancellationToken,
        IEnumerable<string>? approvedCapabilities = null,
        string riskTier = "standard")
    {
        await _lock.WaitAsync(cancellationToken);
        try
        {
            _paths.EnsureDirectories();
            var inspection = await _verifier.VerifyAsync(packagePath, cancellationToken);
            var permission = marketReviewed
                ? _permissions.EvaluateMarket(inspection.Manifest, userGrantedCapabilities)
                : _permissions.Evaluate(inspection.Manifest, userGrantedCapabilities);
            if (permission.DeniedRequired.Count > 0)
            {
                throw new PluginInstallException(
                    $"本地策略或用户未授予必需权限：{string.Join("、", permission.DeniedRequired)}。");
            }

            var requestedCapabilities = inspection.Manifest.Capabilities.Required
                .Concat(inspection.Manifest.Capabilities.Optional)
                .Distinct(StringComparer.Ordinal)
                .Order(StringComparer.Ordinal)
                .ToArray();
            var approvedCapabilitySnapshot = (approvedCapabilities ?? requestedCapabilities)
                .Intersect(requestedCapabilities, StringComparer.Ordinal)
                .Distinct(StringComparer.Ordinal)
                .Order(StringComparer.Ordinal)
                .ToArray();

            var existing = await _registry.GetAsync(inspection.Manifest.PluginId, cancellationToken);
            InstalledPluginVersion? existingVersion = null;
            _ = existing?.Versions.TryGetValue(inspection.Manifest.Version, out existingVersion);
            if (existingVersion is not null
                && existingVersion.PackageSha256 != inspection.PackageSha256)
            {
                throw new PluginInstallException("同一插件版本已存在不同制品，版本不可变。");
            }

            if (existing is not null
                && !string.Equals(
                    existing.CurrentVersion,
                    inspection.Manifest.Version,
                    StringComparison.Ordinal)
                && PluginSemver.Compare(
                    PluginSemver.Parse(inspection.Manifest.Version),
                    PluginSemver.Parse(existing.CurrentVersion)) < 0)
            {
                throw new PluginInstallException(
                    $"目标插件版本 {inspection.Manifest.Version} 低于当前版本 {existing.CurrentVersion}，已拒绝降级安装。请使用回退操作。");
            }

            var cachedPackage = await CachePackageAsync(inspection, cancellationToken);
            var finalDirectory = _paths.InstalledVersionDirectory(
                inspection.Manifest.PluginId,
                inspection.Manifest.Version);
            if (Directory.Exists(finalDirectory) && existingVersion is null)
            {
                throw new PluginInstallException("检测到未登记的同版本安装目录，已拒绝覆盖。");
            }

            var newlyExtracted = false;
            if (!Directory.Exists(finalDirectory))
            {
                var stagingDirectory = Path.Combine(
                    _paths.StagingDirectory,
                    $"{inspection.Manifest.PluginId}-{Guid.NewGuid():N}");
                try
                {
                    Directory.CreateDirectory(stagingDirectory);
                    await ExtractVerifiedAsync(
                        cachedPackage,
                        inspection,
                        stagingDirectory,
                        cancellationToken);
                    Directory.CreateDirectory(Path.GetDirectoryName(finalDirectory)!);
                    Directory.Move(stagingDirectory, finalDirectory);
                    newlyExtracted = true;
                }
                finally
                {
                    DeleteDirectory(stagingDirectory);
                }
            }
            else
            {
                await VerifyInstalledFilesAsync(finalDirectory, inspection, cancellationToken);
            }

            var isUpgrade = existing is not null
                            && existing.CurrentVersion != inspection.Manifest.Version
                            && _validator is IPluginUpgradeValidator;
            var migrationDeclaration = inspection.Manifest.Migration;
            if (isUpgrade
                && migrationDeclaration?.Required == true
                && !migrationDeclaration.FromVersions.Contains(
                    existing!.CurrentVersion,
                    StringComparer.Ordinal))
            {
                throw new PluginInstallException(
                    $"插件迁移声明不支持从 {existing.CurrentVersion} 升级到 {inspection.Manifest.Version}。");
            }
            var migrationWillRun = isUpgrade
                                   && (migrationDeclaration is null
                                       || migrationDeclaration.Required);
            var dataDirectory = _paths.PluginDataDirectory(inspection.Manifest.PluginId);
            var dataExisted = isUpgrade && Directory.Exists(dataDirectory);
            var dataBackup = isUpgrade
                ? Path.Combine(
                    _paths.StagingDirectory,
                    $"migration-data-{inspection.Manifest.PluginId}-{Guid.NewGuid():N}")
                : null;
            var dataBackupReady = false;
            var migrationStarted = false;
            DateTimeOffset? migrationStartedAt = null;
            var migrationRecords = existing?.MigrationRecords?.ToDictionary(
                pair => pair.Key,
                pair => pair.Value,
                StringComparer.Ordinal)
                ?? new Dictionary<string, PluginMigrationRecord>(StringComparer.Ordinal);
            try
            {
                if (dataExisted && dataBackup is not null)
                {
                    CopyDirectory(dataDirectory, dataBackup);
                    dataBackupReady = true;
                }
                if (migrationWillRun && _validator is IPluginUpgradeValidator upgradeValidator)
                {
                    migrationStarted = true;
                    migrationStartedAt = DateTimeOffset.UtcNow;
                    migrationRecords[inspection.Manifest.Version] = new PluginMigrationRecord(
                        existing!.CurrentVersion,
                        inspection.Manifest.Version,
                        "running",
                        migrationStartedAt.Value,
                        null,
                        null,
                        PackageSha256: inspection.PackageSha256);
                    var migrationResult = await upgradeValidator.MigrateAsync(
                        inspection,
                        finalDirectory,
                        existing!.CurrentVersion,
                        permission.Granted,
                        cancellationToken);
                    migrationRecords[inspection.Manifest.Version] = migrationRecords[
                        inspection.Manifest.Version] with
                    {
                        Status = "completed",
                        CompletedAt = DateTimeOffset.UtcNow,
                        Steps = migrationResult.Steps.Select(step => new PluginMigrationStepRecord(
                            step.StepId,
                            step.Status,
                            step.AttemptCount)).ToArray(),
                    };
                }
                else if (isUpgrade)
                {
                    var timestamp = DateTimeOffset.UtcNow;
                    migrationRecords[inspection.Manifest.Version] = new PluginMigrationRecord(
                        existing!.CurrentVersion,
                        inspection.Manifest.Version,
                        "not_required",
                        timestamp,
                        timestamp,
                        null,
                        [],
                        PackageSha256: inspection.PackageSha256);
                }
                await _validator.ValidateAsync(
                    inspection,
                    finalDirectory,
                    permission.Granted,
                    cancellationToken);
                var now = DateTimeOffset.UtcNow;
                var versions = existing?.Versions.ToDictionary(
                    pair => pair.Key,
                    pair => pair.Value,
                    StringComparer.Ordinal)
                    ?? new Dictionary<string, InstalledPluginVersion>(StringComparer.Ordinal);
                versions[inspection.Manifest.Version] = new InstalledPluginVersion(
                    inspection.Manifest.Version,
                    inspection.PackageSha256,
                    inspection.EntryPointPath,
                    inspection.Manifest,
                    now);
                var rollbackVersion = existing is not null
                                      && existing.CurrentVersion != inspection.Manifest.Version
                    ? existing.CurrentVersion
                    : existing?.RollbackVersion;
                var removedVersions = versions.Values
                    .Where(version => version.Version != inspection.Manifest.Version
                                      && version.Version != rollbackVersion)
                    .ToArray();
                var retainedVersions = versions
                    .Where(pair => pair.Key == inspection.Manifest.Version
                                   || pair.Key == rollbackVersion)
                    .ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
                var installed = new InstalledPlugin(
                    inspection.Manifest.PluginId,
                    inspection.Manifest.DisplayName,
                    inspection.Manifest.Description,
                    inspection.Manifest.PublisherKeyId,
                    inspection.PublisherKeyFingerprint,
                    PluginSource.LocalUnreviewed,
                    inspection.Manifest.Version,
                    rollbackVersion,
                    retainedVersions,
                    permission.Granted,
                    Enabled: true,
                    ConsecutiveFailures: 0,
                    RuntimeStatus: "ready",
                    LastError: null,
                    InstalledAt: existing?.InstalledAt ?? now,
                    UpdatedAt: now,
                    LastStartedAt: null,
                    RiskTier: riskTier,
                    PermissionConsents: MergePermissionConsent(
                        existing?.PermissionConsents,
                        inspection.Manifest.Version,
                        requestedCapabilities,
                        approvedCapabilitySnapshot,
                        permission.Granted,
                        inspection.PublisherKeyFingerprint,
                        riskTier,
                        now),
                    MigrationRecords: migrationRecords);
                await _registry.UpsertAsync(installed, cancellationToken);
                CleanupUnretainedVersions(inspection.Manifest.PluginId, retainedVersions.Keys);
                foreach (var removed in removedVersions)
                {
                    await TryDeleteUnreferencedPackageAsync(
                        removed.PackageSha256,
                        inspection.Manifest.PluginId,
                        cancellationToken);
                }

                return new PluginInstallResult(installed, inspection, permission.DeniedOptional);
            }
            catch (Exception installationException)
            {
                if (newlyExtracted)
                {
                    DeleteDirectory(finalDirectory);
                }
                if (migrationStarted)
                {
                    try
                    {
                        DeleteDirectory(dataDirectory);
                        if (dataExisted && dataBackupReady && dataBackup is not null)
                        {
                            CopyDirectory(dataBackup, dataDirectory);
                        }
                    }
                    catch (Exception restoreException)
                        when (restoreException is IOException or UnauthorizedAccessException)
                    {
                        throw new PluginInstallException(
                            "插件升级失败，且无法恢复升级前的私有数据快照。",
                            new AggregateException(installationException, restoreException));
                    }
                }

                if (isUpgrade && existing is not null)
                {
                    var failureTime = DateTimeOffset.UtcNow;
                    var failedRecords = existing.MigrationRecords?.ToDictionary(
                        pair => pair.Key,
                        pair => pair.Value,
                        StringComparer.Ordinal)
                        ?? new Dictionary<string, PluginMigrationRecord>(StringComparer.Ordinal);
                    failedRecords[inspection.Manifest.Version] = new PluginMigrationRecord(
                        existing.CurrentVersion,
                        inspection.Manifest.Version,
                        "failed",
                        migrationStartedAt ?? failureTime,
                        failureTime,
                        installationException.Message.Length > 512
                            ? installationException.Message[..512]
                            : installationException.Message,
                        installationException is PluginMigrationException migrationException
                            ? migrationException.Steps.Select(step => new PluginMigrationStepRecord(
                                step.StepId,
                                step.Status,
                                step.AttemptCount)).ToArray()
                            : [],
                        PackageSha256: inspection.PackageSha256);
                    try
                    {
                        await _registry.UpdateAsync(
                            existing.PluginId,
                            plugin => plugin with
                            {
                                MigrationRecords = failedRecords,
                                UpdatedAt = failureTime,
                            },
                            CancellationToken.None);
                    }
                    catch (Exception)
                    {
                        // Migration failure must preserve the original installation error.
                    }
                }

                throw;
            }
            finally
            {
                TryDeleteDirectory(dataBackup);
            }
        }
        finally
        {
            _lock.Release();
        }
    }

    public async Task<InstalledPlugin> RollbackAsync(
        string pluginId,
        CancellationToken cancellationToken = default)
    {
        await _lock.WaitAsync(cancellationToken);
        try
        {
            var plugin = await _registry.GetAsync(pluginId, cancellationToken)
                ?? throw new PluginInstallException("插件未安装。");
            if (plugin.RollbackVersion is null
                || !plugin.Versions.TryGetValue(plugin.RollbackVersion, out var rollback))
            {
                throw new PluginInstallException("插件没有可回退版本。");
            }

            var directory = _paths.InstalledVersionDirectory(pluginId, rollback.Version);
            var inspection = new PluginPackageInspection(
                string.Empty,
                rollback.PackageSha256,
                rollback.Manifest,
                rollback.EntryPointPath,
                string.Empty,
                plugin.PublisherKeyFingerprint,
                [],
                0);
            await _validator.ValidateAsync(
                inspection,
                directory,
                plugin.GrantedCapabilities,
                cancellationToken);
            var updated = plugin with
            {
                CurrentVersion = rollback.Version,
                RollbackVersion = plugin.CurrentVersion,
                Enabled = true,
                ConsecutiveFailures = 0,
                RuntimeStatus = "ready",
                LastError = null,
                UpdatedAt = DateTimeOffset.UtcNow,
            };
            await _registry.UpsertAsync(updated, cancellationToken);
            return updated;
        }
        finally
        {
            _lock.Release();
        }
    }

    public async Task UninstallAsync(
        string pluginId,
        CancellationToken cancellationToken = default)
    {
        await _lock.WaitAsync(cancellationToken);
        try
        {
            var plugin = await _registry.GetAsync(pluginId, cancellationToken);
            if (plugin is null)
            {
                return;
            }

            var tombstone = Path.Combine(
                _paths.StagingDirectory,
                $"uninstall-{pluginId}-{Guid.NewGuid():N}");
            var installedDirectory = Path.Combine(_paths.InstalledDirectory, pluginId);
            Directory.CreateDirectory(tombstone);
            MoveIfPresent(installedDirectory, Path.Combine(tombstone, "installed"));
            try
            {
                await _registry.RemoveAsync(pluginId, cancellationToken);
            }
            catch
            {
                MoveIfPresent(Path.Combine(tombstone, "installed"), installedDirectory);
                throw;
            }

            try
            {
                DeleteDirectory(tombstone);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }
            foreach (var version in plugin.Versions.Values)
            {
                await TryDeleteUnreferencedPackageAsync(
                    version.PackageSha256,
                    pluginId,
                    cancellationToken);
            }
        }
        finally
        {
            _lock.Release();
        }
    }

    private async Task<string> CachePackageAsync(
        PluginPackageInspection inspection,
        CancellationToken cancellationToken)
    {
        var destination = _paths.PackageCachePath(inspection.PackageSha256);
        if (File.Exists(destination))
        {
            await using var cached = File.OpenRead(destination);
            var cachedHash = Convert.ToHexStringLower(
                await SHA256.HashDataAsync(cached, cancellationToken));
            if (cachedHash == inspection.PackageSha256)
            {
                return destination;
            }

            throw new PluginInstallException("本地插件包缓存摘要不一致。");
        }

        var temporary = $"{destination}.{Guid.NewGuid():N}.tmp";
        try
        {
            await using var source = new FileStream(
                inspection.PackagePath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                FileOptions.Asynchronous | FileOptions.SequentialScan);
            await using (var output = new FileStream(
                             temporary,
                             FileMode.CreateNew,
                             FileAccess.Write,
                             FileShare.None,
                             bufferSize: 64 * 1024,
                             FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await source.CopyToAsync(output, cancellationToken);
                await output.FlushAsync(cancellationToken);
                output.Flush(flushToDisk: true);
            }

            string copiedHash;
            await using (var verify = File.OpenRead(temporary))
            {
                copiedHash = Convert.ToHexStringLower(
                    await SHA256.HashDataAsync(verify, cancellationToken));
            }

            if (copiedHash != inspection.PackageSha256)
            {
                throw new PluginInstallException("插件包在浏览后发生变化，已拒绝安装。");
            }

            File.Move(temporary, destination);
            return destination;
        }
        finally
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
    }

    private static async Task ExtractVerifiedAsync(
        string packagePath,
        PluginPackageInspection inspection,
        string destination,
        CancellationToken cancellationToken)
    {
        var expectedFiles = inspection.Files.ToDictionary(
            file => file.Path,
            file => file,
            StringComparer.OrdinalIgnoreCase);
        await using var stream = File.OpenRead(packagePath);
        using var archive = new ZipArchive(stream, ZipArchiveMode.Read);
        foreach (var expected in expectedFiles.Values)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var entry = archive.Entries.SingleOrDefault(
                item => string.Equals(item.FullName, expected.Path, StringComparison.OrdinalIgnoreCase))
                ?? throw new PluginInstallException($"插件缓存缺少 {expected.Path}。");
            var outputPath = Path.Combine(
                destination,
                expected.Path.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
            await using var entryStream = entry.Open();
            await using (var output = new FileStream(
                             outputPath,
                             FileMode.CreateNew,
                             FileAccess.Write,
                             FileShare.None,
                             bufferSize: 64 * 1024,
                             FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await entryStream.CopyToAsync(output, cancellationToken);
                await output.FlushAsync(cancellationToken);
            }

            await using var extracted = File.OpenRead(outputPath);
            var hash = Convert.ToHexStringLower(
                await SHA256.HashDataAsync(extracted, cancellationToken));
            if (hash != expected.Sha256 || extracted.Length != expected.Length)
            {
                throw new PluginInstallException($"插件文件 {expected.Path} 摘要不一致。");
            }
        }
    }

    private static async Task VerifyInstalledFilesAsync(
        string installedDirectory,
        PluginPackageInspection inspection,
        CancellationToken cancellationToken)
    {
        var expected = inspection.Files.ToDictionary(
            file => file.Path.Replace('/', Path.DirectorySeparatorChar),
            file => file,
            StringComparer.OrdinalIgnoreCase);
        var actualFiles = Directory.EnumerateFiles(
                installedDirectory,
                "*",
                SearchOption.AllDirectories)
            .Select(path => Path.GetRelativePath(installedDirectory, path))
            .ToArray();
        if (actualFiles.Length != expected.Count
            || actualFiles.Any(path => !expected.ContainsKey(path)))
        {
            throw new PluginInstallException("已安装插件目录包含缺失或额外文件。");
        }

        foreach (var (relativePath, file) in expected)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var fullPath = Path.Combine(installedDirectory, relativePath);
            await using var stream = File.OpenRead(fullPath);
            var hash = Convert.ToHexStringLower(
                await SHA256.HashDataAsync(stream, cancellationToken));
            if (stream.Length != file.Length || hash != file.Sha256)
            {
                throw new PluginInstallException($"已安装插件文件 {file.Path} 摘要不一致。");
            }
        }
    }

    private void CleanupUnretainedVersions(string pluginId, IEnumerable<string> retainedVersions)
    {
        var pluginDirectory = Path.Combine(_paths.InstalledDirectory, pluginId);
        if (!Directory.Exists(pluginDirectory))
        {
            return;
        }

        var retained = retainedVersions.ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var directory in Directory.EnumerateDirectories(pluginDirectory))
        {
            if (!retained.Contains(Path.GetFileName(directory)))
            {
                try
                {
                    DeleteDirectory(directory);
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                }
            }
        }
    }

    private static void MoveIfPresent(string source, string destination)
    {
        if (!Directory.Exists(source))
        {
            return;
        }

        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        Directory.Move(source, destination);
    }

    private static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var directory in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(Path.Combine(destination, Path.GetRelativePath(source, directory)));
        }
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var target = Path.Combine(destination, Path.GetRelativePath(source, file));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private static void TryDeleteDirectory(string? path)
    {
        if (path is null)
        {
            return;
        }
        try
        {
            DeleteDirectory(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }

    private async Task TryDeleteUnreferencedPackageAsync(
        string packageSha256,
        string removedPluginId,
        CancellationToken cancellationToken)
    {
        try
        {
            var remaining = await _registry.GetAllAsync(cancellationToken);
            if (remaining.Any(plugin => plugin.PluginId != removedPluginId
                                        && plugin.Versions.Values.Any(
                                            version => version.PackageSha256 == packageSha256)))
            {
                return;
            }

            var path = _paths.PackageCachePath(packageSha256);
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }

    private static IReadOnlyDictionary<string, PluginPermissionConsent> MergePermissionConsent(
        IReadOnlyDictionary<string, PluginPermissionConsent>? existing,
        string version,
        IReadOnlyList<string> requestedCapabilities,
        IReadOnlyList<string> approvedCapabilities,
        IReadOnlyList<string> grantedCapabilities,
        string publisherKeyFingerprint,
        string riskTier,
        DateTimeOffset consentedAt)
    {
        var consents = existing?.ToDictionary(
            pair => pair.Key,
            pair => pair.Value,
            StringComparer.Ordinal)
            ?? new Dictionary<string, PluginPermissionConsent>(StringComparer.Ordinal);
        consents[version] = new PluginPermissionConsent(
            version,
            requestedCapabilities,
            approvedCapabilities,
            grantedCapabilities,
            publisherKeyFingerprint,
            riskTier,
            consentedAt);
        return consents;
    }

    private static void DeleteDirectory(string path)
    {
        if (!Directory.Exists(path))
        {
            return;
        }

        foreach (var file in Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories))
        {
            File.SetAttributes(file, FileAttributes.Normal);
        }

        Directory.Delete(path, recursive: true);
    }

}
