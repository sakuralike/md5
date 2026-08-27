using Microsoft.Win32;
using PasswordDetective.Desktop.Plugins.Market;
using PasswordDetective.Desktop.Plugins.Packages;
using PasswordDetective.Desktop.Plugins.Permissions;
using PasswordDetective.Desktop.Plugins.Registry;
using PasswordDetective.Desktop.Plugins.ViewModels;

namespace PasswordDetective.Desktop.Plugins.UI;

public interface IPluginDialogService
{
    string? SelectPackage();
    string? SelectPath(PluginCommandFieldKind kind);
    bool ConfirmInstall(PluginPackageInspection inspection, PluginPermissionDecision permission);
    bool ConfirmMarketInstall(
        MarketPluginDetail detail,
        MarketPluginVersion version,
        PluginPermissionDecision permission,
        string? currentVersion,
        string? currentRiskTier,
        IReadOnlyList<string> addedCapabilities,
        bool signingKeyChanged,
        bool majorVersionChanged);
    bool ConfirmUninstall(InstalledPlugin plugin);
}

public sealed class PluginDialogService : IPluginDialogService
{
    public string? SelectPackage()
    {
        var dialog = new OpenFileDialog
        {
            Title = "选择本地插件包",
            Filter = "密码侦探社插件包 (*.pdpkg)|*.pdpkg",
            Multiselect = false,
            CheckFileExists = true,
        };
        return dialog.ShowDialog() == true ? dialog.FileName : null;
    }

    public string? SelectPath(PluginCommandFieldKind kind)
    {
        if (kind == PluginCommandFieldKind.Directory)
        {
            var folder = new OpenFolderDialog
            {
                Title = "选择授权目录",
                Multiselect = false,
            };
            return folder.ShowDialog() == true ? folder.FolderName : null;
        }

        var file = new OpenFileDialog
        {
            Title = "选择授权文件",
            Multiselect = false,
            CheckFileExists = true,
        };
        return file.ShowDialog() == true ? file.FileName : null;
    }

    public bool ConfirmInstall(
        PluginPackageInspection inspection,
        PluginPermissionDecision permission)
    {
        var granted = permission.Granted.Count == 0
            ? "无"
            : string.Join("、", permission.Granted);
        var denied = permission.DeniedOptional.Count == 0
            ? "无"
            : string.Join("、", permission.DeniedOptional);
        var message = $"此插件来自本地文件，未经平台审核。\n\n"
                      + $"插件：{inspection.Manifest.DisplayName} {inspection.Manifest.Version}\n"
                      + $"开发者密钥：{inspection.Manifest.PublisherKeyId}\n"
                      + $"将授予：{granted}\n"
                      + $"本地策略拒绝的可选权限：{denied}\n\n"
                      + "安装后仍会持续显示“未审核”。是否继续？";
        return System.Windows.MessageBox.Show(
                   message,
                   "安装未审核本地插件",
                   System.Windows.MessageBoxButton.YesNo,
                   System.Windows.MessageBoxImage.Warning,
                   System.Windows.MessageBoxResult.No)
               == System.Windows.MessageBoxResult.Yes;
    }

    public bool ConfirmMarketInstall(
        MarketPluginDetail detail,
        MarketPluginVersion version,
        PluginPermissionDecision permission,
        string? currentVersion,
        string? currentRiskTier,
        IReadOnlyList<string> addedCapabilities,
        bool signingKeyChanged,
        bool majorVersionChanged)
    {
        var granted = permission.Granted.Count == 0 ? "无" : string.Join("、", permission.Granted);
        var added = addedCapabilities.Count == 0 ? "无" : string.Join("、", addedCapabilities);
        var flags = new List<string>();
        if (signingKeyChanged) flags.Add("开发者签名密钥已变化");
        if (majorVersionChanged) flags.Add("主版本已升级");
        if (IsRiskTierIncreased(currentRiskTier, version.RiskTier)) flags.Add("风险等级已升高");
        var changeText = flags.Count == 0 ? "无" : string.Join("；", flags);
        var installedVersionText = string.IsNullOrWhiteSpace(currentVersion) ? "未安装" : currentVersion;
        var message = $"此插件来自官方在线市场，平台审核策略：{version.ReviewPolicyVersion}。\n\n"
                      + $"插件：{detail.Name} {version.Semver}\n"
                      + $"当前版本：{installedVersionText}\n"
                      + $"开发者：{detail.DeveloperName}\n"
                      + $"风险级别：{version.RiskTier}\n"
                      + $"最近审核：{version.PublishedAt:yyyy-MM-dd HH:mm:ss} UTC\n"
                      + $"将授予权限：{granted}\n"
                      + $"新增权限：{added}\n"
                      + $"需要重新确认的更新变化：{changeText}\n"
                      + $"发布说明：{(string.IsNullOrWhiteSpace(version.ReleaseNotes) ? "无" : version.ReleaseNotes)}\n\n"
                      + "是否继续安装或升级？";
        return System.Windows.MessageBox.Show(
                   message,
                   "确认平台审核插件安装",
                   System.Windows.MessageBoxButton.YesNo,
                   System.Windows.MessageBoxImage.Information,
                   System.Windows.MessageBoxResult.No)
               == System.Windows.MessageBoxResult.Yes;
    }

    public bool ConfirmUninstall(InstalledPlugin plugin) =>
        System.Windows.MessageBox.Show(
            $"卸载插件“{plugin.DisplayName}”？插件私有数据将保留。",
            "卸载插件",
            System.Windows.MessageBoxButton.YesNo,
            System.Windows.MessageBoxImage.Warning,
            System.Windows.MessageBoxResult.No)
        == System.Windows.MessageBoxResult.Yes;

    private static bool IsRiskTierIncreased(string? currentRiskTier, string targetRiskTier)
    {
        if (string.IsNullOrWhiteSpace(currentRiskTier))
        {
            return false;
        }

        return RiskRank(targetRiskTier) > RiskRank(currentRiskTier);
    }

    private static int RiskRank(string value) => value.ToLowerInvariant() switch
    {
        "low" => 1,
        "medium" => 2,
        "high" => 3,
        "critical" => 4,
        _ => 0,
    };
}
