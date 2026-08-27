using Microsoft.Win32.SafeHandles;
using System.IO;
using System.Security.Cryptography;

namespace PasswordDetective.Desktop.Plugins;

public sealed record PluginFileGrant(
    Guid GrantId,
    string FileName,
    long Length);

public sealed class PluginFileBroker : IDisposable
{
    public const int DefaultMaximumChunkBytes = 1024 * 1024;
    public const long DefaultMaximumFileBytes = 1024L * 1024 * 1024;

    private readonly Dictionary<Guid, GrantedFile> _grants = [];
    private readonly object _sync = new();
    private readonly int _maximumChunkBytes;
    private readonly long _maximumFileBytes;
    private bool _disposed;

    public PluginFileBroker(
        int maximumChunkBytes = DefaultMaximumChunkBytes,
        long maximumFileBytes = DefaultMaximumFileBytes)
    {
        if (maximumChunkBytes is < 4096 or > 8 * 1024 * 1024)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumChunkBytes));
        }

        if (maximumFileBytes < maximumChunkBytes)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumFileBytes));
        }

        _maximumChunkBytes = maximumChunkBytes;
        _maximumFileBytes = maximumFileBytes;
    }

    public PluginFileGrant GrantRead(string authorizedPath)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        var fullPath = Path.GetFullPath(authorizedPath);
        var stream = new FileStream(
            fullPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 1,
            FileOptions.Asynchronous | FileOptions.RandomAccess);

        if (stream.Length > _maximumFileBytes)
        {
            stream.Dispose();
            throw new InvalidOperationException("The authorized file exceeds the broker size limit.");
        }

        var grant = new PluginFileGrant(Guid.NewGuid(), Path.GetFileName(fullPath), stream.Length);
        lock (_sync)
        {
            _grants.Add(grant.GrantId, new GrantedFile(stream.SafeFileHandle, stream, stream.Length));
        }

        return grant;
    }

    public async ValueTask<byte[]> ReadAsync(
        Guid grantId,
        long offset,
        int count,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (offset < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(offset));
        }

        if (count is < 1 || count > _maximumChunkBytes)
        {
            throw new ArgumentOutOfRangeException(nameof(count));
        }

        GrantedFile granted;
        lock (_sync)
        {
            if (!_grants.TryGetValue(grantId, out granted!))
            {
                throw new UnauthorizedAccessException("The plugin file grant is missing or revoked.");
            }
        }

        var length = granted.AuthorizedLength;
        if (offset >= length)
        {
            return [];
        }

        var requested = (int)Math.Min(count, length - offset);
        var buffer = GC.AllocateUninitializedArray<byte>(requested);
        var read = await RandomAccess.ReadAsync(
            granted.Handle,
            buffer,
            offset,
            cancellationToken);
        return read == buffer.Length ? buffer : buffer[..read];
    }

    public async ValueTask<string> DigestAsync(
        Guid grantId,
        string algorithm,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        var hashAlgorithm = algorithm.ToLowerInvariant() switch
        {
            "md5" => HashAlgorithmName.MD5,
            "sha1" => HashAlgorithmName.SHA1,
            "sha256" => HashAlgorithmName.SHA256,
            "sha512" => HashAlgorithmName.SHA512,
            _ => throw new ArgumentException("The file digest algorithm is not supported.", nameof(algorithm)),
        };

        GrantedFile granted;
        lock (_sync)
        {
            if (!_grants.TryGetValue(grantId, out granted!))
            {
                throw new UnauthorizedAccessException("The plugin file grant is missing or revoked.");
            }
        }

        using var hash = IncrementalHash.CreateHash(hashAlgorithm);
        var buffer = GC.AllocateUninitializedArray<byte>(_maximumChunkBytes);
        long offset = 0;
        while (offset < granted.AuthorizedLength)
        {
            var requested = (int)Math.Min(buffer.Length, granted.AuthorizedLength - offset);
            var read = await RandomAccess.ReadAsync(
                granted.Handle,
                buffer.AsMemory(0, requested),
                offset,
                cancellationToken);
            if (read == 0)
            {
                throw new IOException("The authorized file ended before its granted length.");
            }

            hash.AppendData(buffer, 0, read);
            offset += read;
        }

        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    public bool Revoke(Guid grantId)
    {
        GrantedFile? granted;
        lock (_sync)
        {
            if (!_grants.Remove(grantId, out granted))
            {
                return false;
            }
        }

        granted.Dispose();
        return true;
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        GrantedFile[] grants;
        lock (_sync)
        {
            grants = [.. _grants.Values];
            _grants.Clear();
        }

        foreach (var grant in grants)
        {
            grant.Dispose();
        }
    }

    private sealed record GrantedFile(
        SafeFileHandle Handle,
        FileStream Stream,
        long AuthorizedLength) : IDisposable
    {
        public void Dispose() => Stream.Dispose();
    }
}
