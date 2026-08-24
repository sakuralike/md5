using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace PasswordDetective.Desktop.Plugins.Windows;

internal sealed class WindowsSandboxedProcess : IAsyncDisposable
{
    private readonly PluginJobObject _job;
    private readonly AppContainerProfile? _profile;
    private readonly SafeKernelObjectHandle _processHandle;
    private readonly int _processId;
    private int? _exitCode;
    private bool _disposed;

    private WindowsSandboxedProcess(
        int processId,
        SafeKernelObjectHandle processHandle,
        PluginJobObject job,
        AppContainerProfile? profile,
        Stream standardInput,
        Stream standardOutput,
        Stream standardError)
    {
        _processId = processId;
        _processHandle = processHandle;
        _job = job;
        _profile = profile;
        StandardInput = standardInput;
        StandardOutput = standardOutput;
        StandardError = standardError;
    }

    public int ProcessId => _processId;
    public bool IsAppContainer => NativeMethods.IsAppContainerProcess(_processHandle);
    public bool HasExited
    {
        get
        {
            RefreshExitCode();
            return _exitCode.HasValue;
        }
    }
    public int? ExitCode
    {
        get
        {
            RefreshExitCode();
            return _exitCode;
        }
    }
    public Stream StandardInput { get; }
    public Stream StandardOutput { get; }
    public Stream StandardError { get; }

    public static WindowsSandboxedProcess Start(PluginProcessStartOptions options)
    {
        options.Validate();
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("The desktop plugin sandbox requires Windows.");
        }

        AppContainerProfile? profile = null;
        PluginJobObject? job = null;
        SafeFileHandle? childStandardInput = null;
        SafeFileHandle? parentStandardInput = null;
        SafeFileHandle? parentStandardOutput = null;
        SafeFileHandle? childStandardOutput = null;
        SafeFileHandle? parentStandardError = null;
        SafeFileHandle? childStandardError = null;
        SafeKernelObjectHandle? retainedProcessHandle = null;
        IntPtr processHandle = IntPtr.Zero;
        IntPtr threadHandle = IntPtr.Zero;

        try
        {
            CreatePipePair(out childStandardInput, out parentStandardInput, childReads: true);
            CreatePipePair(out parentStandardOutput, out childStandardOutput, childReads: false);
            CreatePipePair(out parentStandardError, out childStandardError, childReads: false);

            job = PluginJobObject.Create(options.MemoryLimitBytes, options.ActiveProcessLimit);
            if (options.UseAppContainer)
            {
                profile = AppContainerProfile.Acquire(
                    options.AppContainerProfileName,
                    options.DeleteAppContainerProfileOnDispose);
                profile.GrantDirectory(
                    Path.GetDirectoryName(options.ExecutablePath)!,
                    FileSystemRights.ReadAndExecute | FileSystemRights.Read | FileSystemRights.Synchronize);
                profile.GrantDirectory(
                    options.WorkingDirectory,
                    FileSystemRights.Modify | FileSystemRights.ReadAndExecute | FileSystemRights.Synchronize);
            }

            using var attributes = new ProcessAttributeList(
                childStandardInput,
                childStandardOutput,
                childStandardError,
                profile?.SidPointer);
            var startupInfo = new NativeMethods.StartupInfoEx
            {
                StartupInfo = new NativeMethods.StartupInfo
                {
                    Cb = (uint)Marshal.SizeOf<NativeMethods.StartupInfoEx>(),
                    Flags = NativeMethods.StartfUseStdHandles,
                    StandardInput = childStandardInput.DangerousGetHandle(),
                    StandardOutput = childStandardOutput.DangerousGetHandle(),
                    StandardError = childStandardError.DangerousGetHandle(),
                },
                AttributeList = attributes.Pointer,
            };

            var commandLine = new StringBuilder(CommandLineBuilder.Build(
                options.ExecutablePath,
                options.Arguments));
            using var environment = EnvironmentBlock.Create(options);
            var flags = NativeMethods.CreateSuspended
                | NativeMethods.CreateNoWindow
                | NativeMethods.ExtendedStartupInfoPresent
                | NativeMethods.CreateUnicodeEnvironment;

            if (!NativeMethods.CreateProcess(
                    options.ExecutablePath,
                    commandLine,
                    IntPtr.Zero,
                    IntPtr.Zero,
                    inheritHandles: true,
                    flags,
                    environment.Pointer,
                    options.WorkingDirectory,
                    ref startupInfo,
                    out var processInformation))
            {
                var nativeError = Marshal.GetLastWin32Error();
                throw new Win32Exception(nativeError, $"Unable to start the plugin process (Win32 error {nativeError}).");
            }

            processHandle = processInformation.Process;
            threadHandle = processInformation.Thread;
            job.Assign(processHandle);

            if (NativeMethods.ResumeThread(threadHandle) == uint.MaxValue)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to resume the sandboxed plugin process.");
            }

            childStandardInput.Dispose();
            childStandardInput = null;
            childStandardOutput.Dispose();
            childStandardOutput = null;
            childStandardError.Dispose();
            childStandardError = null;
            NativeMethods.CloseHandle(threadHandle);
            threadHandle = IntPtr.Zero;
            retainedProcessHandle = new SafeKernelObjectHandle(processHandle);
            processHandle = IntPtr.Zero;

            var input = new FileStream(
                parentStandardInput,
                FileAccess.Write,
                bufferSize: 4096,
                isAsync: false);
            parentStandardInput = null;
            var output = new FileStream(
                parentStandardOutput,
                FileAccess.Read,
                bufferSize: 4096,
                isAsync: false);
            parentStandardOutput = null;
            var error = new FileStream(
                parentStandardError,
                FileAccess.Read,
                bufferSize: 4096,
                isAsync: false);
            parentStandardError = null;

            var result = new WindowsSandboxedProcess(
                checked((int)processInformation.ProcessId),
                retainedProcessHandle,
                job,
                profile,
                input,
                output,
                error);
            retainedProcessHandle = null;
            job = null;
            profile = null;
            return result;
        }
        catch
        {
            if (processHandle != IntPtr.Zero)
            {
                NativeMethods.TerminateProcess(processHandle, 1);
            }

            retainedProcessHandle?.Dispose();
            throw;
        }
        finally
        {
            if (threadHandle != IntPtr.Zero)
            {
                NativeMethods.CloseHandle(threadHandle);
            }

            if (processHandle != IntPtr.Zero)
            {
                NativeMethods.CloseHandle(processHandle);
            }

            childStandardInput?.Dispose();
            parentStandardInput?.Dispose();
            parentStandardOutput?.Dispose();
            childStandardOutput?.Dispose();
            parentStandardError?.Dispose();
            childStandardError?.Dispose();
            job?.Dispose();
            profile?.Dispose();
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        await StandardInput.DisposeAsync();
        _job.Dispose();
        try
        {
            var waitResult = NativeMethods.WaitForSingleObject(_processHandle, 5000);
            if (waitResult == NativeMethods.WaitTimeout)
            {
                if (!NativeMethods.TerminateProcess(_processHandle, 1))
                {
                    throw new Win32Exception(
                        Marshal.GetLastWin32Error(),
                        "Unable to terminate the plugin process after its Job Object closed.");
                }

                waitResult = NativeMethods.WaitForSingleObject(_processHandle, 5000);
            }

            if (waitResult == NativeMethods.WaitFailed)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to wait for the plugin process.");
            }

            if (waitResult == NativeMethods.WaitTimeout)
            {
                throw new TimeoutException("The plugin process did not terminate after its Job Object closed.");
            }
        }
        finally
        {
            RefreshExitCode();
            await StandardOutput.DisposeAsync();
            await StandardError.DisposeAsync();
            _processHandle.Dispose();
            _profile?.Dispose();
        }
    }

    private void RefreshExitCode()
    {
        if (_exitCode.HasValue || _processHandle.IsClosed || _processHandle.IsInvalid)
        {
            return;
        }

        if (NativeMethods.GetExitCodeProcess(_processHandle, out var exitCode)
            && exitCode != NativeMethods.StillActive)
        {
            _exitCode = unchecked((int)exitCode);
        }
    }

    private static void CreatePipePair(
        out SafeFileHandle readHandle,
        out SafeFileHandle writeHandle,
        bool childReads)
    {
        var security = new NativeMethods.SecurityAttributes
        {
            Length = Marshal.SizeOf<NativeMethods.SecurityAttributes>(),
            InheritHandle = true,
        };
        if (!NativeMethods.CreatePipe(out readHandle, out writeHandle, ref security, 0))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to create plugin stdio pipes.");
        }

        var parentHandle = childReads ? writeHandle : readHandle;
        if (!NativeMethods.SetHandleInformation(
                parentHandle,
                NativeMethods.HandleFlagInherit,
                0))
        {
            var error = Marshal.GetLastWin32Error();
            readHandle.Dispose();
            writeHandle.Dispose();
            throw new Win32Exception(error, "Unable to protect the parent pipe handle from inheritance.");
        }
    }
}

internal sealed class PluginJobObject : IDisposable
{
    private readonly SafeKernelObjectHandle _handle;

    private PluginJobObject(SafeKernelObjectHandle handle) => _handle = handle;

    public static PluginJobObject Create(long memoryLimitBytes, int activeProcessLimit)
    {
        var handle = NativeMethods.CreateJobObject(IntPtr.Zero, null);
        if (handle.IsInvalid)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to create the plugin Job Object.");
        }

        var information = new NativeMethods.JobObjectExtendedLimitInformation
        {
            BasicLimitInformation = new NativeMethods.JobObjectBasicLimitInformation
            {
                LimitFlags = NativeMethods.JobObjectLimitKillOnJobClose
                    | NativeMethods.JobObjectLimitActiveProcess
                    | NativeMethods.JobObjectLimitProcessMemory
                    | NativeMethods.JobObjectLimitJobMemory,
                ActiveProcessLimit = checked((uint)activeProcessLimit),
            },
            ProcessMemoryLimit = checked((UIntPtr)(ulong)memoryLimitBytes),
            JobMemoryLimit = checked((UIntPtr)(ulong)memoryLimitBytes),
        };

        var size = Marshal.SizeOf<NativeMethods.JobObjectExtendedLimitInformation>();
        var pointer = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(information, pointer, fDeleteOld: false);
            if (!NativeMethods.SetInformationJobObject(
                    handle,
                    NativeMethods.JobObjectInfoType.ExtendedLimitInformation,
                    pointer,
                    checked((uint)size)))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to apply plugin Job Object limits.");
            }
        }
        catch
        {
            handle.Dispose();
            throw;
        }
        finally
        {
            Marshal.FreeHGlobal(pointer);
        }

        return new PluginJobObject(handle);
    }

    public void Assign(IntPtr processHandle)
    {
        if (!NativeMethods.AssignProcessToJobObject(_handle, processHandle))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to assign the plugin to its Job Object.");
        }
    }

    public void Dispose() => _handle.Dispose();
}

internal sealed class AppContainerProfile : IDisposable
{
    private const int AlreadyExistsHResult = unchecked((int)0x800700B7);
    private readonly bool _deleteOnDispose;
    private readonly Dictionary<string, FileSystemAccessRule> _directoryGrants =
        new(StringComparer.OrdinalIgnoreCase);
    private bool _disposed;

    private AppContainerProfile(string name, IntPtr sidPointer, bool deleteOnDispose)
    {
        Name = name;
        SidPointer = sidPointer;
        Sid = new SecurityIdentifier(sidPointer);
        _deleteOnDispose = deleteOnDispose;
    }

    public string Name { get; }
    public IntPtr SidPointer { get; }
    public SecurityIdentifier Sid { get; }

    public static AppContainerProfile Acquire(string name, bool deleteOnDispose)
    {
        var result = NativeMethods.CreateAppContainerProfile(
            name,
            "Password Detective Plugin",
            "Isolated Password Detective plugin host",
            IntPtr.Zero,
            0,
            out var sid);
        var created = result >= 0;
        if (!created)
        {
            if (result != AlreadyExistsHResult)
            {
                Marshal.ThrowExceptionForHR(result);
            }

            result = NativeMethods.DeriveAppContainerSidFromAppContainerName(name, out sid);
            if (result < 0)
            {
                Marshal.ThrowExceptionForHR(result);
            }
        }

        return new AppContainerProfile(name, sid, deleteOnDispose);
    }

    public void GrantDirectory(string path, FileSystemRights rights)
    {
        var fullPath = Path.GetFullPath(path);
        if (_directoryGrants.ContainsKey(fullPath))
        {
            return;
        }

        var directory = new DirectoryInfo(fullPath);
        var security = directory.GetAccessControl(AccessControlSections.Access);
        var rule = new FileSystemAccessRule(
            Sid,
            rights,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None,
            AccessControlType.Allow);
        security.AddAccessRule(rule);
        directory.SetAccessControl(security);
        _directoryGrants.Add(fullPath, rule);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        if (_deleteOnDispose)
        {
            foreach (var (path, rule) in _directoryGrants)
            {
                try
                {
                    var directory = new DirectoryInfo(path);
                    if (!directory.Exists)
                    {
                        continue;
                    }

                    var security = directory.GetAccessControl(AccessControlSections.Access);
                    security.RemoveAccessRuleSpecific(rule);
                    directory.SetAccessControl(security);
                }
                catch (UnauthorizedAccessException)
                {
                }
                catch (IOException)
                {
                }
            }
        }

        NativeMethods.FreeSid(SidPointer);
        if (_deleteOnDispose)
        {
            _ = NativeMethods.DeleteAppContainerProfile(Name);
        }
    }
}

internal sealed class ProcessAttributeList : IDisposable
{
    private readonly IntPtr _securityCapabilities;
    private readonly IntPtr _handleList;

    public ProcessAttributeList(
        SafeFileHandle standardInput,
        SafeFileHandle standardOutput,
        SafeFileHandle standardError,
        IntPtr? appContainerSid)
    {
        var count = appContainerSid.HasValue ? 2 : 1;
        nuint size = 0;
        _ = NativeMethods.InitializeProcThreadAttributeList(IntPtr.Zero, count, 0, ref size);
        if (size == 0)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to size the plugin process attribute list.");
        }

        Pointer = Marshal.AllocHGlobal(checked((int)size));
        if (!NativeMethods.InitializeProcThreadAttributeList(Pointer, count, 0, ref size))
        {
            var error = Marshal.GetLastWin32Error();
            Marshal.FreeHGlobal(Pointer);
            Pointer = IntPtr.Zero;
            throw new Win32Exception(error, "Unable to initialize the plugin process attribute list.");
        }

        try
        {
            var handles = new[]
            {
                standardInput.DangerousGetHandle(),
                standardOutput.DangerousGetHandle(),
                standardError.DangerousGetHandle(),
            };
            _handleList = Marshal.AllocHGlobal(IntPtr.Size * handles.Length);
            Marshal.Copy(handles, 0, _handleList, handles.Length);
            Update(
                NativeMethods.ProcThreadAttributeHandleList,
                _handleList,
                checked((nuint)(IntPtr.Size * handles.Length)));

            if (appContainerSid.HasValue)
            {
                var capabilities = new NativeMethods.SecurityCapabilities
                {
                    AppContainerSid = appContainerSid.Value,
                };
                _securityCapabilities = Marshal.AllocHGlobal(
                    Marshal.SizeOf<NativeMethods.SecurityCapabilities>());
                Marshal.StructureToPtr(capabilities, _securityCapabilities, fDeleteOld: false);
                Update(
                    NativeMethods.ProcThreadAttributeSecurityCapabilities,
                    _securityCapabilities,
                    checked((nuint)Marshal.SizeOf<NativeMethods.SecurityCapabilities>()));
            }
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    public IntPtr Pointer { get; private set; }

    public void Dispose()
    {
        if (Pointer != IntPtr.Zero)
        {
            NativeMethods.DeleteProcThreadAttributeList(Pointer);
            Marshal.FreeHGlobal(Pointer);
            Pointer = IntPtr.Zero;
        }

        if (_securityCapabilities != IntPtr.Zero)
        {
            Marshal.FreeHGlobal(_securityCapabilities);
        }

        if (_handleList != IntPtr.Zero)
        {
            Marshal.FreeHGlobal(_handleList);
        }
    }

    private void Update(IntPtr attribute, IntPtr value, nuint size)
    {
        if (!NativeMethods.UpdateProcThreadAttribute(
                Pointer,
                0,
                attribute,
                value,
                size,
                IntPtr.Zero,
                IntPtr.Zero))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to configure plugin process isolation.");
        }
    }
}

internal sealed class EnvironmentBlock : IDisposable
{
    private EnvironmentBlock(IntPtr pointer) => Pointer = pointer;

    public IntPtr Pointer { get; }

    public static EnvironmentBlock Create(PluginProcessStartOptions options)
    {
        var values = new SortedDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var key in new[]
        {
            "ALLUSERSPROFILE",
            "CommonProgramFiles",
            "CommonProgramFiles(x86)",
            "CommonProgramW6432",
            "ComSpec",
            "NUMBER_OF_PROCESSORS",
            "OS",
            "Path",
            "PATHEXT",
            "PROCESSOR_ARCHITECTURE",
            "PROCESSOR_IDENTIFIER",
            "PROCESSOR_LEVEL",
            "PROCESSOR_REVISION",
            "ProgramData",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramW6432",
            "SystemDrive",
            "SystemRoot",
            "WINDIR",
        })
        {
            AddIfPresent(values, key);
        }

        var profileDirectory = Path.Combine(options.WorkingDirectory, "profile");
        var localAppData = Path.Combine(profileDirectory, "AppData", "Local");
        var roamingAppData = Path.Combine(profileDirectory, "AppData", "Roaming");
        var temporaryDirectory = Path.Combine(localAppData, "Temp");
        Directory.CreateDirectory(temporaryDirectory);
        Directory.CreateDirectory(roamingAppData);

        var workingRoot = Path.GetPathRoot(profileDirectory) ?? string.Empty;
        values["APPDATA"] = roamingAppData;
        values["HOMEDRIVE"] = workingRoot.TrimEnd(Path.DirectorySeparatorChar);
        values["HOMEPATH"] = Path.DirectorySeparatorChar + profileDirectory[workingRoot.Length..];
        values["LOCALAPPDATA"] = Environment.GetEnvironmentVariable("LOCALAPPDATA") ?? localAppData;
        values["TEMP"] = temporaryDirectory;
        values["TMP"] = temporaryDirectory;
        values["USERPROFILE"] = profileDirectory;
        foreach (var (key, value) in options.Environment)
        {
            values[key] = value;
        }

        var block = string.Join('\0', values.Select(pair => $"{pair.Key}={pair.Value}")) + "\0\0";
        return new EnvironmentBlock(Marshal.StringToHGlobalUni(block));
    }

    public void Dispose() => Marshal.FreeHGlobal(Pointer);

    private static void AddIfPresent(IDictionary<string, string> values, string key)
    {
        var value = Environment.GetEnvironmentVariable(key);
        if (!string.IsNullOrWhiteSpace(value))
        {
            values[key] = value;
        }
    }
}

internal static class CommandLineBuilder
{
    public static string Build(string executablePath, IReadOnlyList<string> arguments)
    {
        return string.Join(' ', new[] { executablePath }.Concat(arguments).Select(Quote));
    }

    private static string Quote(string value)
    {
        if (value.Length > 0 && value.All(character => !char.IsWhiteSpace(character) && character != '"'))
        {
            return value;
        }

        var result = new StringBuilder("\"");
        var backslashes = 0;
        foreach (var character in value)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }

            if (character == '"')
            {
                result.Append('\\', backslashes * 2 + 1);
                result.Append('"');
                backslashes = 0;
                continue;
            }

            result.Append('\\', backslashes);
            backslashes = 0;
            result.Append(character);
        }

        result.Append('\\', backslashes * 2);
        result.Append('"');
        return result.ToString();
    }
}

internal sealed class SafeKernelObjectHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    public SafeKernelObjectHandle() : base(ownsHandle: true)
    {
    }

    internal SafeKernelObjectHandle(IntPtr existingHandle) : base(ownsHandle: true)
    {
        SetHandle(existingHandle);
    }

    protected override bool ReleaseHandle() => NativeMethods.CloseHandle(handle);
}

internal static class NativeMethods
{
    internal const uint StartfUseStdHandles = 0x00000100;
    internal const uint CreateSuspended = 0x00000004;
    internal const uint CreateUnicodeEnvironment = 0x00000400;
    internal const uint ExtendedStartupInfoPresent = 0x00080000;
    internal const uint CreateNoWindow = 0x08000000;
    internal const uint HandleFlagInherit = 0x00000001;
    internal const uint JobObjectLimitActiveProcess = 0x00000008;
    internal const uint JobObjectLimitProcessMemory = 0x00000100;
    internal const uint JobObjectLimitJobMemory = 0x00000200;
    internal const uint JobObjectLimitKillOnJobClose = 0x00002000;
    internal const uint StillActive = 259;
    internal const uint WaitTimeout = 258;
    internal const uint WaitFailed = uint.MaxValue;
    internal const uint TokenQuery = 0x0008;
    internal static readonly IntPtr ProcThreadAttributeHandleList = (IntPtr)0x00020002;
    internal static readonly IntPtr ProcThreadAttributeSecurityCapabilities = (IntPtr)0x00020009;

    [StructLayout(LayoutKind.Sequential)]
    internal struct SecurityAttributes
    {
        internal int Length;
        internal IntPtr SecurityDescriptor;
        [MarshalAs(UnmanagedType.Bool)] internal bool InheritHandle;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    internal struct StartupInfo
    {
        internal uint Cb;
        internal string? Reserved;
        internal string? Desktop;
        internal string? Title;
        internal uint X;
        internal uint Y;
        internal uint XSize;
        internal uint YSize;
        internal uint XCountChars;
        internal uint YCountChars;
        internal uint FillAttribute;
        internal uint Flags;
        internal ushort ShowWindow;
        internal ushort Reserved2;
        internal IntPtr ReservedData;
        internal IntPtr StandardInput;
        internal IntPtr StandardOutput;
        internal IntPtr StandardError;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct StartupInfoEx
    {
        internal StartupInfo StartupInfo;
        internal IntPtr AttributeList;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct ProcessInformation
    {
        internal IntPtr Process;
        internal IntPtr Thread;
        internal uint ProcessId;
        internal uint ThreadId;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct SecurityCapabilities
    {
        internal IntPtr AppContainerSid;
        internal IntPtr Capabilities;
        internal uint CapabilityCount;
        internal uint Reserved;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct JobObjectBasicLimitInformation
    {
        internal long PerProcessUserTimeLimit;
        internal long PerJobUserTimeLimit;
        internal uint LimitFlags;
        internal UIntPtr MinimumWorkingSetSize;
        internal UIntPtr MaximumWorkingSetSize;
        internal uint ActiveProcessLimit;
        internal UIntPtr Affinity;
        internal uint PriorityClass;
        internal uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct IoCounters
    {
        internal ulong ReadOperationCount;
        internal ulong WriteOperationCount;
        internal ulong OtherOperationCount;
        internal ulong ReadTransferCount;
        internal ulong WriteTransferCount;
        internal ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct JobObjectExtendedLimitInformation
    {
        internal JobObjectBasicLimitInformation BasicLimitInformation;
        internal IoCounters IoInfo;
        internal UIntPtr ProcessMemoryLimit;
        internal UIntPtr JobMemoryLimit;
        internal UIntPtr PeakProcessMemoryUsed;
        internal UIntPtr PeakJobMemoryUsed;
    }

    internal enum JobObjectInfoType
    {
        ExtendedLimitInformation = 9,
    }

    internal enum TokenInformationClass
    {
        TokenIsAppContainer = 29,
    }

    internal static bool IsAppContainerProcess(SafeKernelObjectHandle process)
    {
        if (!OpenProcessToken(process, TokenQuery, out var token))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to open the plugin process token.");
        }

        using (token)
        {
            var value = 0;
            if (!GetTokenInformation(
                    token,
                    TokenInformationClass.TokenIsAppContainer,
                    ref value,
                    sizeof(int),
                    out _))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to inspect the plugin process token.");
            }

            return value != 0;
        }
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreatePipe(
        out SafeFileHandle readPipe,
        out SafeFileHandle writePipe,
        ref SecurityAttributes pipeAttributes,
        uint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetHandleInformation(
        SafeFileHandle handle,
        uint mask,
        uint flags);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    internal static extern SafeKernelObjectHandle CreateJobObject(
        IntPtr jobAttributes,
        string? name);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetInformationJobObject(
        SafeKernelObjectHandle job,
        JobObjectInfoType infoType,
        IntPtr jobObjectInfo,
        uint jobObjectInfoLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool AssignProcessToJobObject(
        SafeKernelObjectHandle job,
        IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool InitializeProcThreadAttributeList(
        IntPtr attributeList,
        int attributeCount,
        int flags,
        ref nuint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool UpdateProcThreadAttribute(
        IntPtr attributeList,
        uint flags,
        IntPtr attribute,
        IntPtr value,
        nuint size,
        IntPtr previousValue,
        IntPtr returnSize);

    [DllImport("kernel32.dll")]
    internal static extern void DeleteProcThreadAttributeList(IntPtr attributeList);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateProcess(
        string applicationName,
        StringBuilder commandLine,
        IntPtr processAttributes,
        IntPtr threadAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool inheritHandles,
        uint creationFlags,
        IntPtr environment,
        string currentDirectory,
        ref StartupInfoEx startupInfo,
        out ProcessInformation processInformation);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint ResumeThread(IntPtr thread);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool TerminateProcess(IntPtr process, uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool TerminateProcess(
        SafeKernelObjectHandle process,
        uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetExitCodeProcess(
        SafeKernelObjectHandle process,
        out uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint WaitForSingleObject(
        SafeKernelObjectHandle handle,
        uint milliseconds);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool OpenProcessToken(
        SafeKernelObjectHandle process,
        uint desiredAccess,
        out SafeAccessTokenHandle token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetTokenInformation(
        SafeAccessTokenHandle token,
        TokenInformationClass tokenInformationClass,
        ref int tokenInformation,
        int tokenInformationLength,
        out int returnLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CloseHandle(IntPtr handle);

    [DllImport("userenv.dll", CharSet = CharSet.Unicode)]
    internal static extern int CreateAppContainerProfile(
        string appContainerName,
        string displayName,
        string description,
        IntPtr capabilities,
        uint capabilityCount,
        out IntPtr appContainerSid);

    [DllImport("userenv.dll", CharSet = CharSet.Unicode)]
    internal static extern int DeriveAppContainerSidFromAppContainerName(
        string appContainerName,
        out IntPtr appContainerSid);

    [DllImport("userenv.dll", CharSet = CharSet.Unicode)]
    internal static extern int DeleteAppContainerProfile(string appContainerName);

    [DllImport("advapi32.dll")]
    internal static extern IntPtr FreeSid(IntPtr sid);
}
