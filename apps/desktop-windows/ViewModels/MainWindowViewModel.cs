using System.ComponentModel;
using System.Runtime.CompilerServices;
using Microsoft.Win32;
using PasswordDetective.Desktop.Infrastructure;
using PasswordDetective.Desktop.Models;
using PasswordDetective.Desktop.Services;
using System.IO;

namespace PasswordDetective.Desktop.ViewModels;

public sealed class MainWindowViewModel : INotifyPropertyChanged
{
    private readonly IFileFingerprintService _fingerprintService;
    private CancellationTokenSource? _cancellation;
    private string _selectedFile = string.Empty;
    private string _status = "请选择 ZIP 或 7z 文件。文件内容不会上传。";
    private double _progress;
    private bool _isBusy;
    private FileFingerprintResult? _result;

    public MainWindowViewModel(IFileFingerprintService fingerprintService)
    {
        _fingerprintService = fingerprintService;
        SelectFileCommand = new RelayCommand(SelectFile, () => !IsBusy);
        CalculateCommand = new AsyncRelayCommand(CalculateAsync, () => !IsBusy && File.Exists(SelectedFile));
        CancelCommand = new RelayCommand(Cancel, () => IsBusy);
    }

    public string SelectedFile
    {
        get => _selectedFile;
        private set { SetField(ref _selectedFile, value); NotifyCommands(); }
    }

    public string Status { get => _status; private set => SetField(ref _status, value); }
    public double Progress { get => _progress; private set => SetField(ref _progress, value); }
    public FileFingerprintResult? Result { get => _result; private set => SetField(ref _result, value); }

    public bool IsBusy
    {
        get => _isBusy;
        private set { SetField(ref _isBusy, value); NotifyCommands(); }
    }

    public RelayCommand SelectFileCommand { get; }
    public AsyncRelayCommand CalculateCommand { get; }
    public RelayCommand CancelCommand { get; }

    private void SelectFile()
    {
        var dialog = new OpenFileDialog
        {
            Title = "选择压缩包",
            Filter = "首版支持 (*.zip;*.7z)|*.zip;*.7z|所有文件 (*.*)|*.*",
            CheckFileExists = true,
            Multiselect = false,
        };
        if (dialog.ShowDialog() == true)
        {
            SelectedFile = dialog.FileName;
            Result = null;
            Progress = 0;
            Status = "文件已选择，准备在本地计算 SHA-256 和 MD5。";
        }
    }

    private async Task CalculateAsync()
    {
        IsBusy = true;
        Result = null;
        Progress = 0;
        Status = "正在读取文件并计算指纹…";
        _cancellation = new CancellationTokenSource();
        var progress = new Progress<double>(value => Progress = value * 100);
        try
        {
            Result = await _fingerprintService.CalculateAsync(
                SelectedFile, progress, _cancellation.Token);
            Status = "计算完成。当前阶段不会上传文件或自动提交指纹。";
        }
        catch (OperationCanceledException)
        {
            Status = "计算已取消。";
        }
        catch (Exception)
        {
            Status = "计算失败，请确认文件可读后重试。";
        }
        finally
        {
            _cancellation.Dispose();
            _cancellation = null;
            IsBusy = false;
        }
    }

    private void Cancel() => _cancellation?.Cancel();

    private void NotifyCommands()
    {
        SelectFileCommand.NotifyCanExecuteChanged();
        CalculateCommand.NotifyCanExecuteChanged();
        CancelCommand.NotifyCanExecuteChanged();
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        return true;
    }

    public event PropertyChangedEventHandler? PropertyChanged;
}
