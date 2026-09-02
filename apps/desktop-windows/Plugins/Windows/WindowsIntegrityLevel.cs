using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace PasswordDetective.Desktop.Plugins.Windows;

internal static class WindowsIntegrityLevel
{
    private const uint TokenAdjustDefault = 0x0080;
    private const uint TokenQuery = 0x0008;
    private const uint TokenIntegrityLevel = 25;
    private const uint LabelSecurityInformation = 0x0000_0020;

    public static void LowerCurrentProcessToLow()
    {
        if (!OpenProcessToken(
            GetCurrentProcess(),
            TokenAdjustDefault | TokenQuery,
            out var token))
        {
            throw new InvalidOperationException("无法打开 Host.Sandbox 令牌。");
        }

        var sid = IntPtr.Zero;
        var label = IntPtr.Zero;
        try
        {
            if (!ConvertStringSidToSid("S-1-16-4096", out sid))
            {
                throw new InvalidOperationException("无法创建 Low Integrity SID。");
            }

            var labelSize = Marshal.SizeOf<TokenMandatoryLabel>();
            label = Marshal.AllocHGlobal(labelSize);
            Marshal.StructureToPtr(
                new TokenMandatoryLabel
                {
                    Label = new SidAndAttributes
                    {
                        Sid = sid,
                        Attributes = LabelSecurityInformation,
                    },
                },
                label,
                fDeleteOld: false);
            if (!SetTokenInformation(
                token,
                TokenIntegrityLevel,
                label,
                checked((uint)labelSize)))
            {
                throw new InvalidOperationException("无法将 Host.Sandbox 降至 Low Integrity。");
            }
        }
        finally
        {
            if (label != IntPtr.Zero)
            {
                Marshal.FreeHGlobal(label);
            }

            if (sid != IntPtr.Zero)
            {
                LocalFree(sid);
            }

            token.Dispose();
        }

        if (!string.Equals(GetCurrent(), "low", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Host.Sandbox Low Integrity 断言失败。");
        }
    }

    public static string GetCurrent()
    {
        if (!OpenProcessToken(GetCurrentProcess(), TokenQuery, out var token))
        {
            return "unknown";
        }

        try
        {
            GetTokenInformation(token, TokenIntegrityLevel, IntPtr.Zero, 0, out var required);
            if (required == 0)
            {
                return "unknown";
            }

            var buffer = Marshal.AllocHGlobal(checked((int)required));
            try
            {
                if (!GetTokenInformation(token, TokenIntegrityLevel, buffer, required, out _))
                {
                    return "unknown";
                }

                var label = Marshal.PtrToStructure<TokenMandatoryLabel>(buffer);
                var count = Marshal.ReadByte(label.Label.Sid, 1);
                var rid = Marshal.ReadInt32(label.Label.Sid, 8 + (count - 1) * 4);
                return rid switch
                {
                    <= 0x1000 => "low",
                    <= 0x2000 => "medium",
                    _ => "high",
                };
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
        finally
        {
            token.Dispose();
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SidAndAttributes
    {
        public IntPtr Sid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenMandatoryLabel
    {
        public SidAndAttributes Label;
    }

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(
        IntPtr processHandle,
        uint desiredAccess,
        out SafeAccessTokenHandle tokenHandle);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ConvertStringSidToSid(string stringSid, out IntPtr sid);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memory);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetTokenInformation(
        SafeAccessTokenHandle tokenHandle,
        uint tokenInformationClass,
        IntPtr tokenInformation,
        uint tokenInformationLength);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetTokenInformation(
        SafeAccessTokenHandle tokenHandle,
        uint tokenInformationClass,
        IntPtr tokenInformation,
        uint tokenInformationLength,
        out uint returnLength);
}
