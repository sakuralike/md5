using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Runtime.CompilerServices;
using System.Text.Json;
using PasswordDetective.Desktop.Infrastructure;
using PasswordDetective.Desktop.Plugins.Packages;

namespace PasswordDetective.Desktop.Plugins.ViewModels;

public enum PluginCommandFieldKind
{
    Text,
    Integer,
    Number,
    Boolean,
    Enum,
    File,
    Directory,
}

public sealed class PluginCommandFieldViewModel : INotifyPropertyChanged
{
    private readonly Func<PluginCommandFieldKind, string?> _browse;
    private string _value = string.Empty;
    private bool _booleanValue;

    internal PluginCommandFieldViewModel(
        string name,
        string label,
        PluginCommandFieldKind kind,
        bool required,
        IReadOnlyList<string> options,
        Func<PluginCommandFieldKind, string?> browse)
    {
        Name = name;
        Label = label;
        Kind = kind;
        Required = required;
        Options = options;
        _browse = browse;
        BrowseCommand = new RelayCommand(Browse, () => kind is PluginCommandFieldKind.File or PluginCommandFieldKind.Directory);
        if (kind == PluginCommandFieldKind.Enum && options.Count > 0)
        {
            _value = options[0];
        }
    }

    public string Name { get; }
    public string Label { get; }
    public PluginCommandFieldKind Kind { get; }
    public bool Required { get; }
    public IReadOnlyList<string> Options { get; }
    public bool IsBoolean => Kind == PluginCommandFieldKind.Boolean;
    public bool IsEnum => Kind == PluginCommandFieldKind.Enum;
    public bool IsPath => Kind is PluginCommandFieldKind.File or PluginCommandFieldKind.Directory;
    public bool IsText => !IsBoolean && !IsEnum && !IsPath;
    public RelayCommand BrowseCommand { get; }

    public string Value
    {
        get => _value;
        set => SetField(ref _value, value);
    }

    public bool BooleanValue
    {
        get => _booleanValue;
        set => SetField(ref _booleanValue, value);
    }

    public JsonElement ToJson()
    {
        if (Required && Kind != PluginCommandFieldKind.Boolean && string.IsNullOrWhiteSpace(Value))
        {
            throw new InvalidOperationException($"请填写 {Label}。");
        }

        return Kind switch
        {
            PluginCommandFieldKind.Boolean => JsonSerializer.SerializeToElement(BooleanValue),
            PluginCommandFieldKind.Integer when long.TryParse(
                Value,
                NumberStyles.Integer,
                CultureInfo.InvariantCulture,
                out var integer) => JsonSerializer.SerializeToElement(integer),
            PluginCommandFieldKind.Number when decimal.TryParse(
                Value,
                NumberStyles.Number,
                CultureInfo.InvariantCulture,
                out var number) => JsonSerializer.SerializeToElement(number),
            PluginCommandFieldKind.Integer => throw new InvalidOperationException($"{Label} 必须是整数。"),
            PluginCommandFieldKind.Number => throw new InvalidOperationException($"{Label} 必须是数字。"),
            _ => JsonSerializer.SerializeToElement(Value),
        };
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    private void Browse()
    {
        var path = _browse(Kind);
        if (!string.IsNullOrWhiteSpace(path))
        {
            Value = path;
        }
    }

    private void SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return;
        }

        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}

public sealed class PluginCommandForm
{
    private PluginCommandForm(IReadOnlyList<PluginCommandFieldViewModel> fields) =>
        Fields = new ObservableCollection<PluginCommandFieldViewModel>(fields);

    public ObservableCollection<PluginCommandFieldViewModel> Fields { get; }

    public static PluginCommandForm Load(
        string schemaPath,
        Func<PluginCommandFieldKind, string?> browse)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(schemaPath), new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 32,
        });
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty("type", out var type)
            || type.GetString() != "object"
            || !root.TryGetProperty("properties", out var properties)
            || properties.ValueKind != JsonValueKind.Object)
        {
            throw new PluginPackageException("命令输入 Schema 必须声明 object properties。");
        }

        var required = root.TryGetProperty("required", out var requiredElement)
            ? requiredElement.EnumerateArray()
                .Select(item => item.GetString() ?? string.Empty)
                .ToHashSet(StringComparer.Ordinal)
            : [];
        var fields = new List<PluginCommandFieldViewModel>();
        foreach (var property in properties.EnumerateObject())
        {
            if (fields.Count >= 32 || property.Name.Length is < 1 or > 128)
            {
                throw new PluginPackageException("命令输入字段数量或名称无效。");
            }

            var schema = property.Value;
            var label = schema.TryGetProperty("title", out var title)
                ? title.GetString() ?? property.Name
                : property.Name;
            if (label.Length is < 1 or > 100)
            {
                throw new PluginPackageException("命令输入字段标题无效。");
            }

            var options = schema.TryGetProperty("enum", out var enumElement)
                ? enumElement.EnumerateArray()
                    .Select(item => item.GetString()
                                    ?? throw new PluginPackageException("枚举输入只支持字符串值。"))
                    .ToArray()
                : [];
            var fieldType = schema.TryGetProperty("type", out var fieldTypeElement)
                ? fieldTypeElement.GetString()
                : null;
            var format = schema.TryGetProperty("format", out var formatElement)
                ? formatElement.GetString()
                : null;
            var kind = ResolveKind(fieldType, format, options.Length > 0);
            fields.Add(new PluginCommandFieldViewModel(
                property.Name,
                label,
                kind,
                required.Contains(property.Name),
                options,
                browse));
        }

        return new PluginCommandForm(fields);
    }

    public JsonElement BuildInput()
    {
        var values = Fields.ToDictionary(
            field => field.Name,
            field => field.ToJson(),
            StringComparer.Ordinal);
        return JsonSerializer.SerializeToElement(values);
    }

    private static PluginCommandFieldKind ResolveKind(
        string? type,
        string? format,
        bool hasEnum)
    {
        if (hasEnum && type == "string")
        {
            return PluginCommandFieldKind.Enum;
        }

        return (type, format) switch
        {
            ("string", "file") => PluginCommandFieldKind.File,
            ("string", "directory") => PluginCommandFieldKind.Directory,
            ("string", _) => PluginCommandFieldKind.Text,
            ("integer", _) => PluginCommandFieldKind.Integer,
            ("number", _) => PluginCommandFieldKind.Number,
            ("boolean", _) => PluginCommandFieldKind.Boolean,
            _ => throw new PluginPackageException("命令输入 Schema 包含宿主不支持的字段类型。"),
        };
    }
}
