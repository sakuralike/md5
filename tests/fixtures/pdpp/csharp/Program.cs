using System.Diagnostics;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

if (args is ["--child"])
{
    await Task.Delay(Timeout.InfiniteTimeSpan);
    return;
}

while (await Console.In.ReadLineAsync() is { } line)
{
    using var document = JsonDocument.Parse(line);
    var root = document.RootElement;
    var id = root.GetProperty("id").GetString()!;
    var method = root.GetProperty("method").GetString()!;
    var parameters = root.GetProperty("params");

    switch (method)
    {
        case "initialize":
            await WriteResultAsync(id, new
            {
                protocol_version = "1.0",
                plugin_id = parameters.GetProperty("plugin_id").GetString(),
                plugin_version = "1.0.0",
                capabilities = new[] { "command.echo", "synthetic.faults" },
            });
            break;
        case "health/check":
            await WriteResultAsync(id, new { status = "healthy" });
            break;
        case "lifecycle/migrate":
            await WriteResultAsync(id, new { status = "not_required", steps = Array.Empty<object>() });
            break;
        case "command/execute":
            await ExecuteCommandAsync(id, parameters);
            break;
        case "shutdown":
            await WriteResultAsync(id, new { stopped = true });
            return;
        default:
            await WriteErrorAsync(id, -32601, "Method not found");
            break;
    }
}

static async Task ExecuteCommandAsync(string id, JsonElement parameters)
{
    var command = parameters.GetProperty("command").GetString();
    var input = parameters.GetProperty("input");
    switch (command)
    {
        case "echo":
            await WriteResultAsync(id, new
            {
                output = input,
                language = "csharp",
            });
            return;
        case "hang":
            await Task.Delay(Timeout.InfiniteTimeSpan);
            return;
        case "crash":
            Console.Error.Write("synthetic crash");
            Environment.Exit(23);
            return;
        case "spawn-child":
            using (var child = Process.Start(new ProcessStartInfo
            {
                FileName = Environment.ProcessPath!,
                Arguments = "--child",
                UseShellExecute = false,
                CreateNoWindow = true,
            }))
            {
                await WriteResultAsync(id, new
                {
                    child_pid = child!.Id,
                    language = "csharp",
                });
            }
            return;
        case "allocate":
            var allocations = new List<byte[]>();
            while (true)
            {
                allocations.Add(GC.AllocateUninitializedArray<byte>(8 * 1024 * 1024));
                allocations[^1][0] = 1;
                await Task.Yield();
            }
        case "probe":
            var fileRead = false;
            try
            {
                _ = await File.ReadAllTextAsync(input.GetProperty("file_path").GetString()!);
                fileRead = true;
            }
            catch
            {
            }

            var networkConnected = false;
            try
            {
                using var client = new TcpClient();
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
                await client.ConnectAsync(
                    input.GetProperty("host").GetString()!,
                    input.GetProperty("port").GetInt32(),
                    timeout.Token);
                networkConnected = true;
            }
            catch
            {
            }

            await WriteResultAsync(id, new
            {
                file_read = fileRead,
                network_connected = networkConnected,
                language = "csharp",
            });
            return;
        case "environment":
            await WriteResultAsync(id, new
            {
                present = Environment.GetEnvironmentVariable(input.GetString()!) is not null,
                language = "csharp",
            });
            return;
        case "oversized-output":
            await WriteResultAsync(id, new
            {
                output = new string('x', 16 * 1024),
                language = "csharp",
            });
            return;
        case "malformed-envelope":
            await Console.Out.WriteLineAsync($"{{\"jsonrpc\":2,\"id\":\"{id}\",\"result\":{{}}}}");
            await Console.Out.FlushAsync();
            return;
        case "host-file-read":
            var descriptor = input.GetProperty("file");
            await WriteAsync(new
            {
                jsonrpc = "2.0",
                id = "plugin-file-read-1",
                method = "host/file/read",
                @params = new
                {
                    file_ref = descriptor.GetProperty("file_ref").GetString(),
                    offset = 0,
                    count = Math.Min(descriptor.GetProperty("length").GetInt32(), 4096),
                },
            });
            var hostResponseLine = await Console.In.ReadLineAsync()
                ?? throw new InvalidOperationException("Host callback response is missing.");
            using (var hostResponse = JsonDocument.Parse(hostResponseLine))
            {
                var result = hostResponse.RootElement.GetProperty("result");
                var content = Encoding.UTF8.GetString(
                    Convert.FromBase64String(result.GetProperty("data_base64").GetString()!));
                await WriteResultAsync(id, new
                {
                    content,
                    language = "csharp",
                });
            }
            return;
        default:
            await WriteErrorAsync(id, -32602, "Unknown synthetic command");
            return;
    }
}

static Task WriteResultAsync(string id, object result) => WriteAsync(new
{
    jsonrpc = "2.0",
    id,
    result,
});

static Task WriteErrorAsync(string id, int code, string message) => WriteAsync(new
{
    jsonrpc = "2.0",
    id,
    error = new { code, message },
});

static async Task WriteAsync(object response)
{
    await Console.Out.WriteLineAsync(JsonSerializer.Serialize(response));
    await Console.Out.FlushAsync();
}
