using Microsoft.Win32;
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

    public bool ConfirmUninstall(InstalledPlugin plugin) =>
        System.Windows.MessageBox.Show(
            $"卸载未审核插件“{plugin.DisplayName}”及其私有数据？",
            "卸载插件",
            System.Windows.MessageBoxButton.YesNo,
            System.Windows.MessageBoxImage.Warning,
            System.Windows.MessageBoxResult.No)
        == System.Windows.MessageBoxResult.Yes;
}
