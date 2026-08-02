using PasswordDetective.Desktop.Models;

namespace PasswordDetective.Desktop.Services;

public static class DesktopRecoveryAdvisor
{
    public static DesktopRecoveryAdvice From(DesktopApiException exception) =>
        exception.Code switch
        {
            "desktop.installation_revoked" => new(
                "当前安装身份已被撤销。请生成新的安装身份并重新注册。",
                CanRegenerateInstallation: true,
                UpgradeRequired: false),
            "desktop.installation_account_mismatch" => new(
                "当前安装身份已绑定其他账号。请生成新的安装身份，再用当前账号注册。",
                CanRegenerateInstallation: true,
                UpgradeRequired: false),
            "desktop.installation_key_mismatch" => new(
                "本地安装密钥与服务端记录不一致。请生成新的安装身份并重新注册。",
                CanRegenerateInstallation: true,
                UpgradeRequired: false),
            "desktop.installation_not_found" => new(
                "服务端未找到当前安装身份。请生成新的安装身份并重新注册。",
                CanRegenerateInstallation: true,
                UpgradeRequired: false),
            "desktop.installation_limit_reached" => new(
                "安装实例数量已达上限。请先在账号中撤销不再使用的旧实例。",
                CanRegenerateInstallation: false,
                UpgradeRequired: false),
            "desktop.client_version_unsupported" => UnsupportedVersion(exception),
            _ => new(
                $"服务端请求失败（{exception.Code}）：{exception.Message}",
                CanRegenerateInstallation: false,
                UpgradeRequired: false),
        };

    private static DesktopRecoveryAdvice UnsupportedVersion(DesktopApiException exception)
    {
        var minimumVersion = exception.GetStringDetail("minimum_client_version");
        var message = string.IsNullOrWhiteSpace(minimumVersion)
            ? "当前客户端版本不受支持，请升级到服务端要求的版本后重试。"
            : $"当前客户端版本不受支持，请升级到 {minimumVersion} 或更高版本后重试。";
        return new DesktopRecoveryAdvice(
            message,
            CanRegenerateInstallation: false,
            UpgradeRequired: true);
    }
}
