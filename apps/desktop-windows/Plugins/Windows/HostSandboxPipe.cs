using System.IO.Pipes;
using System.IO;
using System.Text;

namespace PasswordDetective.Desktop.Plugins.Windows;

/// <summary>
/// Bounded JSON-lines transport between Host.UI and Host.Sandbox.
/// The pipe name is per host session and must never be reused across sessions.
/// </summary>
internal sealed class HostSandboxPipe : IAsyncDisposable
{
    private const int MaxMessageBytes = 1024 * 1024;
    private readonly string _name;
    private readonly NamedPipeServerStream _pipe;
    private readonly StreamReader _reader;
    private readonly StreamWriter _writer;

    private HostSandboxPipe(string name, NamedPipeServerStream pipe)
    {
        _name = name;
        _pipe = pipe;
        _reader = new StreamReader(
            pipe,
            new UTF8Encoding(false, true),
            detectEncodingFromByteOrderMarks: false,
            bufferSize: 4096,
            leaveOpen: true);
        _writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, leaveOpen: true)
        {
            AutoFlush = true,
            NewLine = "\n",
        };
    }

    public string Name => _name;

    public static HostSandboxPipe CreateServer(string name)
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("Host.Sandbox IPC requires Windows.");
        }

        if (string.IsNullOrWhiteSpace(name) || name.Length > 80 || name.Any(char.IsWhiteSpace))
        {
            throw new ArgumentException("Pipe name is invalid.", nameof(name));
        }

        var pipe = new NamedPipeServerStream(
            name,
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous | PipeOptions.WriteThrough);
        return new HostSandboxPipe(name, pipe);
    }

    public Task ConnectAsync(CancellationToken cancellationToken = default) =>
        _pipe.WaitForConnectionAsync(cancellationToken);

    public async Task SendAsync(string message, CancellationToken cancellationToken = default)
    {
        if (Encoding.UTF8.GetByteCount(message) > MaxMessageBytes)
        {
            throw new InvalidDataException("Host.Sandbox message exceeds the 1 MiB limit.");
        }

        await _writer.WriteLineAsync(message.AsMemory(), cancellationToken).ConfigureAwait(false);
    }

    public async Task<string?> ReceiveAsync(CancellationToken cancellationToken = default)
    {
        var builder = new StringBuilder(capacity: 4096);
        var character = new char[1];
        while (true)
        {
            var read = await _reader.ReadAsync(character.AsMemory(), cancellationToken)
                .ConfigureAwait(false);
            if (read == 0)
            {
                return builder.Length == 0 ? null : builder.ToString();
            }

            if (character[0] == '\n')
            {
                return builder.ToString();
            }

            if (character[0] == '\r')
            {
                continue;
            }

            if (builder.Length >= MaxMessageBytes)
            {
                throw new InvalidDataException("Host.Sandbox message exceeds the 1 MiB limit.");
            }

            builder.Append(character[0]);
        }
    }

    public ValueTask DisposeAsync()
    {
        _writer.Dispose();
        _reader.Dispose();
        return _pipe.DisposeAsync();
    }
}
